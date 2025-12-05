import pandas as pd
from services.portfolio_service import calculate_liquidity
def parse_degiro_csv(file):
    df = pd.read_csv(file)
    cols = ['Quantità', 'Quotazione', 'Valore', 'Costi di transazione', 'Totale']
    for c in cols:
        if c in df.columns:
            df[c] = df[c].astype(str).str.replace(',', '.').apply(pd.to_numeric, errors='coerce').fillna(0)
    if 'Data' in df.columns:
        df['Data'] = pd.to_datetime(df['Data'], format='%d-%m-%Y', errors='coerce').dt.normalize()
    if 'Costi di transazione' in df.columns:
        df['Costi di transazione'] = df['Costi di transazione'].abs()
    return df

def generate_id(row, index):
    d_str = row['Data'].strftime('%Y-%m-%d') if pd.notna(row['Data']) else ""
    raw = f"{index}{d_str}{row.get('Ora','')}{row.get('ISIN','')}{row.get('Quantità','')}{row.get('Valore','')}"
    return hashlib.md5(raw.encode()).hexdigest()

def process_new_transactions(file: "UploadedFile", existing_transactions: pd.DataFrame) -> pd.DataFrame:
    """
    Elabora un file CSV di transazioni, lo confronta con quelle esistenti e restituisce solo le nuove.
    """
    ndf = parse_degiro_csv(file)
    rows_to_add = []
    existing_ids = set(existing_transactions['id']) if not existing_transactions.empty else set()
    
    for idx, r in ndf.iterrows():
        if pd.isna(r.get('ISIN')): continue
        tid = generate_id(r, idx)
        if tid not in existing_ids:
            val = r.get('Totale', 0) if r.get('Totale', 0) != 0 else r.get('Valore', 0)
            rows_to_add.append({
                'id': tid, 
                'date': r['Data'], 
                'product': r.get('Prodotto',''), 
                'isin': r.get('ISIN',''), 
                'quantity': r.get('Quantità',0), 
                'local_value': val, 
                'fees': r.get('Costi di transazione',0), 
                'currency': 'EUR'
            })
            existing_ids.add(tid)
            
    return pd.DataFrame(rows_to_add)

def calculate_net_worth_snapshot(snapshot_date: pd.Timestamp, df_trans: pd.DataFrame, df_map: pd.DataFrame, df_prices: pd.DataFrame, df_budget: pd.DataFrame) -> tuple[float, float, float]:
    """
    Calcola il valore degli asset, la liquidità e il patrimonio netto totale a una data specifica.
    Replica la logica complessa della pagina Gestione Dati.
    """
    # Normalizza le date per confronti sicuri
    if not df_trans.empty: df_trans['date'] = pd.to_datetime(df_trans['date']).dt.normalize()
    if not df_prices.empty: df_prices['date'] = pd.to_datetime(df_prices['date']).dt.normalize()
    if not df_budget.empty: df_budget['date'] = pd.to_datetime(df_budget['date']).dt.normalize()

    net_worth_at_date, total_assets_value, final_liquidity = 0, 0, 0

    # Filtra tutti i dati fino alla data dello snapshot
    trans_at_date = df_trans[df_trans['date'] <= snapshot_date] if not df_trans.empty else pd.DataFrame()
    prices_at_date = df_prices[df_prices['date'] <= snapshot_date] if not df_prices.empty else pd.DataFrame()
    budget_at_date = df_budget[df_budget['date'] <= snapshot_date] if not df_budget.empty else pd.DataFrame()

    # 1. Calcolo Valore Asset alla data
    if not trans_at_date.empty and not df_map.empty and not prices_at_date.empty:
        df_full_nw = trans_at_date.merge(df_map, on='isin', how='left')
        last_prices_at_date = prices_at_date.sort_values('date').groupby('ticker').tail(1).set_index('ticker')['close_price']
        view_nw = df_full_nw.groupby('ticker')['quantity'].sum().reset_index()
        view_nw['mkt_val'] = view_nw['quantity'] * view_nw['ticker'].map(last_prices_at_date).fillna(0)
        total_assets_value = view_nw['mkt_val'].sum()

    # 2. Calcolo Liquidità alla data (usando la funzione di servizio già esistente)
    final_liquidity, _ = calculate_liquidity(budget_at_date, trans_at_date)

    # 3. Calcolo Patrimonio Netto
    net_worth_at_date = total_assets_value + final_liquidity
    
    return net_worth_at_date, total_assets_value, final_liquidity

def fetch_justetf_allocation_robust(isin):
    """
    Scarica da JustETF usando un metodo robusto basato su BeautifulSoup
    che cerca le intestazioni 'Paesi' e 'Settori' per identificare le tabelle corrette,
    indipendentemente dalla loro posizione nella pagina.
    """
    url = f"https://www.justetf.com/it/etf-profile.html?isin={isin}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7"
    }

    geo_dict, sec_dict = {}, {}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'lxml')
        
        # --- ESTRAZIONE DATI GEOGRAFIA ---
        h3_geo = soup.find('h3', string=lambda text: text and 'Paesi' in text)
        if h3_geo:
            table = h3_geo.find_next('table')
            if table:
                for row in table.find_all('tr'):
                    cols = row.find_all('td')
                    if len(cols) >= 2:
                        key = cols[0].text.strip()
                        val_str = cols[1].text.strip().replace('%', '').replace(',', '.')
                        try:
                            val = float(val_str)
                            if val < 101: geo_dict[key] = val
                        except (ValueError, TypeError):
                            pass
        
        # --- ESTRAZIONE DATI SETTORI ---
        h3_sec = soup.find('h3', string=lambda text: text and 'Settori' in text)
        if h3_sec:
            table = h3_sec.find_next('table')
            if table:
                for row in table.find_all('tr'):
                    cols = row.find_all('td')
                    if len(cols) >= 2:
                        key = cols[0].text.strip()
                        val_str = cols[1].text.strip().replace('%', '').replace(',', '.')
                        try:
                            val = float(val_str)
                            if val < 101: sec_dict[key] = val
                        except (ValueError, TypeError):
                            pass
                            
        return geo_dict, sec_dict

    except Exception as e:
        st.error(f"Scraping fallito per {isin}: {e}")
        return {}, {}
    

def sync_prices(df_trans, df_map):
    if df_trans.empty or df_map.empty: return 0
    df_full = df_trans.merge(df_map, on='isin', how='left')
    holdings = df_full.groupby('ticker')['quantity'].sum()
    owned_tickers = holdings[holdings > 0.001].index.dropna().tolist()
    if not owned_tickers: return 0

    df_prices_all = get_data("prices")
    if not df_prices_all.empty:
        # Assicuriamoci che la colonna 'date' sia 'datetime' e senza fuso orario per confronti sicuri
        df_prices_all['date'] = pd.to_datetime(df_prices_all['date'], errors='coerce').dt.tz_localize(None).dt.normalize()
    
    new_data = []
    errors = []
    bar = st.progress(0, text="Sincronizzazione prezzi...")
    
    # Definiamo "oggi" e "ieri"
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)

    for i, t in enumerate(owned_tickers):
        start_date = "2020-01-01"
        needs_update = True
        
        if not df_prices_all.empty:
            exist = df_prices_all[df_prices_all['ticker'] == t]
            if not exist.empty:
                last_price_date = exist['date'].max().date()
                
                # Se abbiamo già i dati fino a ieri, siamo a posto.
                if last_price_date >= yesterday:
                    needs_update = False
                else:
                    start_date = (last_price_date + timedelta(days=1)).strftime('%Y-%m-%d')

        if needs_update:
            bar.progress((i + 1) / len(owned_tickers), text=f"Scaricando {t} dal {start_date}...")
            try:
                # Scarica i dati
                hist = yf.download(t, start=start_date, progress=False)
                
                # --- FIX PER YFINANCE RECENTE (MultiIndex) ---
                if isinstance(hist.columns, pd.MultiIndex):
                    try:
                        if t in hist.columns.get_level_values(1):
                            hist = hist.xs(t, axis=1, level=1)
                        else:
                            hist.columns = hist.columns.get_level_values(0)
                    except Exception:
                        hist.columns = hist.columns.get_level_values(0)

                if not hist.empty and 'Close' in hist.columns:
                    for d, v in hist['Close'].items():
                        # --- FILTRO FONDAMENTALE ---
                        # Salviamo SOLO se la data del dato è STRETTAMENTE PRECEDENTE a oggi.
                        # Questo scarta qualsiasi prezzo "live" o "intraday" di oggi.
                        if pd.notna(v) and d.date() < today: 
                            new_data.append({'ticker': t, 'date': d.normalize().tz_localize(None), 'close_price': float(v)})
                else:
                    if hist.empty:
                        print(f"Nessun dato trovato per {t} dal {start_date}")
            except Exception as e: 
                errors.append(f"{t}: {str(e)}")
        else:
            bar.progress((i + 1) / len(owned_tickers), text=f"{t} già aggiornato.")
    
    if errors:
        st.warning(f"Problemi con alcuni ticker: {', '.join(errors)}")

    if new_data:
        df_new = pd.DataFrame(new_data)
        df_new['date'] = pd.to_datetime(df_new['date']).dt.normalize()
        save_data(df_new, "prices", method='append')
        return len(df_new)
    
    return 0