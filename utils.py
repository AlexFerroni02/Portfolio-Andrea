import streamlit as st
import pandas as pd
import yfinance as yf
import hashlib
import gspread
from google.oauth2.service_account import Credentials
from datetime import date, timedelta, datetime

# --- GOOGLE SHEETS ---
@st.cache_resource
def get_google_sheet_client():
    try:
        secrets = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(
            secrets,
            scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        )
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Errore Secrets: {e}")
        return None

# --- CACHING (TTL 10 min) ---
@st.cache_data(ttl=600)
def get_data(sheet_name):
    client = get_google_sheet_client()
    if not client: return pd.DataFrame()
    try:
        sh = client.open("PortfolioDB")
        wks = sh.worksheet(sheet_name)
        data = wks.get_all_records()
        return pd.DataFrame(data)
    except: return pd.DataFrame()

# --- SALVATAGGIO E PULIZIA CACHE ---
def save_data(df, sheet_name):
    client = get_google_sheet_client()
    if not client: return
    try:
        sh = client.open("PortfolioDB")
        try: wks = sh.worksheet(sheet_name)
        except: wks = sh.add_worksheet(title=sheet_name, rows=1000, cols=20)
        wks.clear()
        if not df.empty:
            df_str = df.astype(str)
            wks.update([df_str.columns.values.tolist()] + df_str.values.tolist())
        
        # *** PUNTO CRUCIALE: SVUOTA LA CACHE ***
        # Questo costringe Streamlit a riscaricare i dati freschi alla prossima chiamata
        get_data.clear()
        
    except Exception as e: st.error(f"Errore salvataggio {sheet_name}: {e}")

# --- PARSING & LOGICA ---
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

def sync_prices(tickers):
    if not tickers: return 0
    df_prices = get_data("prices")
    
    if not df_prices.empty:
        df_prices['date'] = pd.to_datetime(df_prices['date'], errors='coerce').dt.normalize()
        df_prices = df_prices.dropna(subset=['date'])
    
    new_data = []
    bar = st.progress(0)
    for i, t in enumerate(tickers):
        start_date = "2020-01-01"
        if not df_prices.empty:
            exist = df_prices[df_prices['ticker'] == t]
            if not exist.empty:
                last = exist['date'].max()
                if pd.notna(last) and last.date() < (date.today() - timedelta(days=1)):
                    start_date = (last + timedelta(days=1)).strftime('%Y-%m-%d')
                elif pd.notna(last):
                    bar.progress((i+1)/len(tickers))
                    continue
        try:
            hist = yf.download(t, start=start_date, progress=False)
            if not hist.empty:
                closes = hist['Close']
                if isinstance(closes, pd.DataFrame): closes = closes.iloc[:,0]
                for d, v in closes.items():
                    if pd.notna(v):
                        new_data.append({'ticker': t, 'date': d.strftime('%Y-%m-%d'), 'close_price': float(v)})
        except: pass
        bar.progress((i+1)/len(tickers))
    bar.empty()
    
    if new_data:
        df_new = pd.DataFrame(new_data)
        df_new['date'] = pd.to_datetime(df_new['date'])
        
        # Filtra solo i dati effettivamente nuovi
        df_combined = pd.concat([df_prices, df_new], ignore_index=True)
        df_combined = df_combined.drop_duplicates(subset=['ticker', 'date'], keep='first')
        
        # Calcola quanti dati sono effettivamente nuovi
        num_new_prices = len(df_combined) - len(df_prices)
        
        # Salva solo se ci sono nuovi dati
        if num_new_prices > 0:
            save_data(df_combined, "prices")
        return num_new_prices
    
    return 0

def color_pnl(val):
    try:
        v = float(str(val).strip('%'))
        color = '#d4edda' if v >= 0 else '#f8d7da'
        text_color = '#155724' if v >= 0 else '#721c24'
        return f'background-color: {color}; color: {text_color}'
    except: return ''

def make_sidebar():
    with st.sidebar:
        st.header("Navigazione")
        st.page_link("app.py", label="Dashboard", icon="🏠")
        st.page_link("pages/2_Gestione_Dati.py", label="Gestione Dati", icon="📂")
        st.page_link("pages/3_Benchmark.py", label="Benchmark", icon="⚖️")
        st.divider()