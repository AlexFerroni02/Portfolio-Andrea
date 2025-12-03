import streamlit as st
import pandas as pd
import yfinance as yf
import hashlib
from datetime import date, timedelta, datetime
import requests
import json
from sqlalchemy import text
from bs4 import BeautifulSoup
# --- CONNESSIONE AL DATABASE (NEON/POSTGRESQL) ---
@st.cache_resource
def get_db_connection():
    """Stabilisce la connessione al DB usando i secrets di Streamlit."""
    return st.connection("postgresql", type="sql")

# --- LETTURA DATI (CON CACHE STRUTTURALE) ---
@st.cache_data(ttl=600)
def get_data(table_name):
    """Legge un'intera tabella dal database."""
    try:
        conn = get_db_connection()
        df = conn.query(f'SELECT * FROM "{table_name}";', ttl=5) 
        return df
    except Exception:
        return pd.DataFrame()

# --- SALVATAGGIO DATI ---
def save_data(df, table_name, method='replace'):
    """Salva un DataFrame in una tabella e pulisce la cache globale."""
    try:
        conn = get_db_connection()
        df.to_sql(name=table_name, con=conn.engine, if_exists=method, index=False)
        # Pulisce la cache di TUTTE le funzioni @st.cache_data.
        # Questo è il metodo corretto per forzare un refresh dei dati in tutta l'app.
        st.cache_data.clear()
    except Exception as e:
        st.error(f"Errore durante il salvataggio della tabella '{table_name}': {e}")

# --- FUNZIONI DI LOGICA ---

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

def color_pnl(val):
    v = 0
    try:
        if isinstance(val, (int, float)): v = val
        else: v = float(str(val).replace('%', '').strip())
        color = '#d4edda' if v >= 0 else '#f8d7da'
        text_color = '#155724' if v >= 0 else '#721c24'
        return f'background-color: {color}; color: {text_color}'
    except (ValueError, TypeError): return ''
    
def style_chart_for_mobile(fig):
    fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1), margin=dict(l=10, r=10, t=40, b=10), hovermode="x unified", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return fig

def make_sidebar():
    with st.sidebar:
        st.page_link("app.py", label="Dashboard", icon="🏠")
        st.page_link("pages/1_Analisi_Asset.py", label="Analisi Asset", icon="🔎")
        st.page_link("pages/2_Gestione_Dati.py", label="Gestione Dati", icon="📂")
        st.page_link("pages/3_Benchmark.py", label="Benchmark", icon="⚖️")
        st.page_link("pages/4_Bilancio.py", label="Bilancio", icon="💰")
        
        st.divider()
        st.caption(f"Portfolio Pro v1.2\n© {datetime.now().year}")

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

def save_allocation_json(ticker, geo_dict, sec_dict):
    """Salva i dizionari come JSON nel DB usando UPSERT."""
    conn = get_db_connection()
    geo_json = json.dumps(geo_dict, ensure_ascii=False)
    sec_json = json.dumps(sec_dict, ensure_ascii=False)
    
    query = text("""
        INSERT INTO asset_allocation (ticker, geography_json, sector_json, last_updated)
        VALUES (:t, :g, :s, NOW())
        ON CONFLICT (ticker) DO UPDATE 
        SET geography_json = :g, sector_json = :s, last_updated = NOW();
    """)
    
    with conn.session as s:
        s.execute(query, {'t': ticker, 'g': geo_json, 's': sec_json})
        s.commit()
    
    get_data.clear()