import streamlit as st
import pandas as pd
import yfinance as yf
import hashlib
from datetime import date, timedelta, datetime
import requests
from bs4 import BeautifulSoup
from sqlalchemy import text
from playwright.sync_api import sync_playwright
import json
# --- CONNESSIONE AL DATABASE (NEON/POSTGRESQL) ---
@st.cache_resource
def get_db_connection():
    """Stabilisce la connessione al DB usando i secrets di Streamlit. Questa funzione è cachata per l'intera sessione."""
    return st.connection("postgresql", type="sql")

# --- LETTURA DATI (CON CACHE STRUTTURALE) ---
@st.cache_data(ttl=600)
def get_data(table_name):
    """
    Legge un'intera tabella dal database.
    I dati vengono cachati. La cache viene invalidata esplicitamente da save_data().
    """
    try:
        conn = get_db_connection()
        df = conn.query(f'SELECT * FROM "{table_name}";', ttl=5) 
        return df
    except Exception:
        return pd.DataFrame()

# --- SALVATAGGIO DATI (CON INVALIDAZIONE CACHE) ---
def save_data(df, table_name, method='replace'):
    """
    Salva un DataFrame in una tabella.
    - method='replace': Sovrascrive l'intera tabella (default).
    - method='append': Aggiunge le nuove righe in fondo alla tabella.
    """
    try:
        conn = get_db_connection()
        df.to_sql(name=table_name, con=conn.engine, if_exists=method, index=False)
        get_data.clear()
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
        df_prices_all['date'] = pd.to_datetime(df_prices_all['date'], errors='coerce').dt.normalize()
    
    new_data = []
    bar = st.progress(0, text="Sincronizzazione prezzi...")
    for i, t in enumerate(owned_tickers):
        start_date = "2020-01-01"
        if not df_prices_all.empty:
            exist = df_prices_all[df_prices_all['ticker'] == t]
            if not exist.empty:
                last = exist['date'].max()
                if pd.notna(last) and last.date() < (date.today() - timedelta(days=1)):
                    start_date = (last + timedelta(days=1)).strftime('%Y-%m-%d')
                elif pd.notna(last):
                    bar.progress((i + 1) / len(owned_tickers), text=f"{t} già aggiornato.")
                    continue
        try:
            hist = yf.download(t, start=start_date, progress=False)
            if not hist.empty:
                for d, v in hist['Close'].items():
                    if pd.notna(v): new_data.append({'ticker': t, 'date': d, 'close_price': float(v)})
        except Exception: pass
        bar.progress((i + 1) / len(owned_tickers), text=f"Scaricati prezzi per {t}")
    
    if new_data:
        df_new = pd.DataFrame(new_data)
        save_data(df_new, "prices", method='append')
        return len(df_new)
    return 0

def color_pnl(val):
    try:
        v = float(str(val).strip('%'))
        color = '#d4edda' if v >= 0 else '#f8d7da'
        text_color = '#155724' if v >= 0 else '#721c24'
        return f'background-color: {color}; color: {text_color}'
    except: return ''
    
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
        st.page_link("pages/5_Allocazione.py", label="X-Ray Portafoglio", icon="🌍")
        st.divider()
        st.caption(f"Portfolio Pro v1.0\n© {datetime.now().year}")

def fetch_yahoo_allocation(ticker):
    """Scarica dati settoriali/geografici da Yahoo (funziona bene su Azioni e ETF USA)"""
    try:
        t = yf.Ticker(ticker)
        info = t.info
        data = {}

        # SE È AZIONE SINGOLA
        if info.get('quoteType') == 'EQUITY':
            country = info.get('country', '').lower()
            if 'united states' in country: data['geo_us'] = 100
            elif 'canada' in country: data['geo_ca'] = 100
            elif 'japan' in country: data['geo_jp'] = 100
            elif any(c in country for c in ['united kingdom', 'france', 'germany', 'switzerland', 'spain', 'italy', 'netherlands', 'sweden']): data['geo_eu_w'] = 100
            else: data['geo_other'] = 100
            
            sector = info.get('sector', '').lower()
            if 'technology' in sector: data['sec_tech'] = 100
            elif 'financial' in sector: data['sec_fin'] = 100
            elif 'healthcare' in sector: data['sec_health'] = 100
            elif 'communication' in sector: data['sec_comm'] = 100
            elif 'consumer cyclical' in sector: data['sec_cons_cyc'] = 100
            elif 'consumer defensive' in sector: data['sec_cons_def'] = 100
            elif 'industrials' in sector: data['sec_ind'] = 100
            elif 'energy' in sector: data['sec_energy'] = 100
            elif 'basic materials' in sector: data['sec_mat'] = 100
            elif 'real estate' in sector: data['sec_real'] = 100
            elif 'utilities' in sector: data['sec_util'] = 100
            return data
            
        # SE È ETF (Cerca i pesi settoriali e geografici)
        if info.get('quoteType') == 'ETF':
            # Settori
            if info.get('sectorWeightings'):
                sector_map = {'technology': 'sec_tech', 'financialservices': 'sec_fin', 'healthcare': 'sec_health', 'communicationservices': 'sec_comm', 'consumercyclical': 'sec_cons_cyc', 'consumerdefensive': 'sec_cons_def', 'energy': 'sec_energy', 'industrials': 'sec_ind', 'basicmaterials': 'sec_mat', 'realestate': 'sec_real', 'utilities': 'sec_util'}
                for item in info['sectorWeightings']:
                    for key, value in item.items():
                        sector_key = sector_map.get(key.replace(" ", "").lower())
                        if sector_key: data[sector_key] = float(value) * 100
            # Geografia
            if info.get('countryWeightings'):
                geo_map_eu = ['united kingdom', 'france', 'germany', 'switzerland', 'spain', 'italy', 'netherlands', 'sweden', 'ireland', 'denmark', 'finland', 'norway', 'belgium', 'austria', 'portugal']
                for item in info['countryWeightings']:
                    for key, value in item.items():
                        country_lower = key.lower()
                        if country_lower == 'united states': data['geo_us'] = data.get('geo_us', 0) + float(value) * 100
                        elif country_lower == 'canada': data['geo_ca'] = data.get('geo_ca', 0) + float(value) * 100
                        elif country_lower == 'japan': data['geo_jp'] = data.get('geo_jp', 0) + float(value) * 100
                        elif any(c in country_lower for c in geo_map_eu): data['geo_eu_w'] = data.get('geo_eu_w', 0) + float(value) * 100
                        elif 'china' in country_lower or 'india' in country_lower: data['geo_em_asia'] = data.get('geo_em_asia', 0) + float(value) * 100
                        elif 'taiwan' in country_lower or 'korea' in country_lower or 'australia' in country_lower: data['geo_pac'] = data.get('geo_pac', 0) + float(value) * 100
                        else: data['geo_other'] = data.get('geo_other', 0) + float(value) * 100
            return data if data else None
        return None
    except: return None


def fetch_justetf_allocation_json(isin):
    """
    Scarica da JustETF fingendosi un browser reale.
    """
    url = f"https://www.justetf.com/it/etf-profile.html?isin={isin}"
    
    # TRUCCO: Ci mascheriamo da Browser vero per non farci bloccare
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7"
    }

    try:
        # 1. Scarichiamo l'HTML grezzo con requests
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status() # Controlla se ci sono errori 403/404
        
        # 2. Leggiamo le tabelle dall'HTML scaricato
        # Nota: thousands='.' e decimal=',' sono fondamentali per l'Italia
        dfs = pd.read_html(response.text, decimal=',', thousands='.')
        
        geo_dict = {}
        sec_dict = {}
        
        # 3. Analizziamo tutte le tabelle trovate
        for df in dfs:
            if df.shape[1] >= 2: # Deve avere almeno 2 colonne (Nome, Valore)
                # Pulizia colonne: a volte la prima è l'etichetta, la seconda il valore
                # Convertiamo tutto in stringa per cercare parole chiave
                df_str = df.astype(str)
                
                # Cerchiamo di capire che tabella è guardando il contenuto della prima colonna
                first_col_values = " ".join(df_str.iloc[:, 0].tolist()).lower()
                
                # TABELLA GEOGRAFIA? (Cerca parole chiave geografiche)
                if any(x in first_col_values for x in ['stati uniti', 'giappone', 'europa', 'mondo', 'regno unito']):
                    for _, row in df.iterrows():
                        key = str(row[0]).strip()
                        val_raw = str(row[1]).replace('%', '').strip()
                        try:
                            val = float(val_raw.replace(',', '.'))
                            # JustETF a volte mette "Etf" o "Indice" come intestazioni, ignoriamole
                            if val < 101: 
                                geo_dict[key] = val
                        except: pass
                
                # TABELLA SETTORI? (Cerca parole chiave settoriali)
                elif any(x in first_col_values for x in ['tecnologia', 'finanza', 'salute', 'industria', 'beni di consumo']):
                    for _, row in df.iterrows():
                        key = str(row[0]).strip()
                        val_raw = str(row[1]).replace('%', '').strip()
                        try:
                            val = float(val_raw.replace(',', '.'))
                            if val < 101:
                                sec_dict[key] = val
                        except: pass

        # 4. Mappatura intelligente dei nomi (JustETF -> Nostro DB)
        # Convertiamo i nomi italiani di JustETF nei nomi delle colonne del nostro DB o JSON standard
        
        # (Opzionale: qui potresti normalizzare i nomi, ma salvarli così va bene uguale
        # perché il grafico a torta aggregherà le etichette stringa)
        
        return geo_dict, sec_dict

    except Exception as e:
        print(f"Errore Scraper JustETF ({isin}): {e}")
        return {}, {}

def save_allocation_json(ticker, geo_dict, sec_dict):
    """Salva i dizionari come JSON nel DB"""
    conn = get_db_connection()
    
    # Converti dict in stringa JSON
    geo_json = json.dumps(geo_dict, ensure_ascii=False)
    sec_json = json.dumps(sec_dict, ensure_ascii=False)
    
    # Query UPSERT (Insert or Update)
    query = text("""
        INSERT INTO asset_allocation (ticker, geography_json, sector_json, last_updated)
        VALUES (:t, :g, :s, NOW())
        ON CONFLICT (ticker) DO UPDATE 
        SET geography_json = :g, sector_json = :s, last_updated = NOW();
    """)
    
    with conn.session as s:
        s.execute(query, {'t': ticker, 'g': geo_json, 's': sec_json})
        s.commit()
    
    # Invalida la cache per asset_allocation
    get_data.clear()