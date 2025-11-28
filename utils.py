import streamlit as st
import pandas as pd
import yfinance as yf
import hashlib
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, date

# --- CONNESSIONE DATABASE ---
@st.cache_resource
def get_google_sheet_client():
    secrets = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(
        secrets,
        scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    )
    return gspread.authorize(creds)

def get_data(sheet_name):
    client = get_google_sheet_client()
    try:
        sh = client.open("PortfolioDB")
        wks = sh.worksheet(sheet_name)
        data = wks.get_all_records()
        return pd.DataFrame(data)
    except: return pd.DataFrame()

def save_data(df, sheet_name):
    client = get_google_sheet_client()
    try:
        sh = client.open("PortfolioDB")
        try: wks = sh.worksheet(sheet_name)
        except: wks = sh.add_worksheet(title=sheet_name, rows=1000, cols=20)
        wks.clear()
        if not df.empty:
            df_str = df.astype(str)
            wks.update([df_str.columns.values.tolist()] + df_str.values.tolist())
    except Exception as e: st.error(f"Errore salvataggio {sheet_name}: {e}")

# --- PARSING E CALCOLI ---
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
    """Genera ID usando anche l'indice di riga per evitare duplicati"""
    d_str = row['Data'].strftime('%Y-%m-%d') if pd.notna(row['Data']) else ""
    raw = f"{index}{d_str}{row['Ora']}{row['ISIN']}{row.get('ID Ordine','')}{row['Quantità']}{row['Valore']}"
    return hashlib.md5(raw.encode()).hexdigest()

def sync_prices(tickers):
    if not tickers: return 0
    df_prices = get_data("prices")
    
    # Pulizia date nel DB
    if not df_prices.empty:
        df_prices['date'] = pd.to_datetime(df_prices['date'], errors='coerce').dt.normalize()
        df_prices = df_prices.dropna(subset=['date'])
    
    new_data = []
    
    for t in tickers:
        start_date = "2020-01-01"
        if not df_prices.empty:
            exist = df_prices[df_prices['ticker'] == t]
            if not exist.empty:
                last = exist['date'].max()
                # Scarica solo se mancano dati da ieri
                if pd.notna(last) and last.date() < (date.today() - timedelta(days=1)):
                    start_date = (last + timedelta(days=1)).strftime('%Y-%m-%d')
                elif pd.notna(last): continue
        try:
            hist = yf.download(t, start=start_date, progress=False)
            if not hist.empty:
                closes = hist['Close']
                if isinstance(closes, pd.DataFrame): closes = closes.iloc[:,0]
                for d, v in closes.items():
                    if pd.notna(v):
                        new_data.append({'ticker': t, 'date': d.strftime('%Y-%m-%d'), 'close_price': float(v)})
        except: pass
    
    if new_data:
        df_new = pd.DataFrame(new_data)
        df_new['date'] = pd.to_datetime(df_new['date'])
        df_fin = pd.concat([df_prices, df_new], ignore_index=True).drop_duplicates(subset=['ticker', 'date'])
        save_data(df_fin, "prices")
        return len(new_data)
    return 0

def load_and_clean_data():
    """Carica tutto per le pagine"""
    df_t = get_data("transactions")
    df_m = get_data("mapping")
    df_p = get_data("prices")
    
    if df_t.empty or df_m.empty or df_p.empty: return None, None, None, None
    
    df_t['date'] = pd.to_datetime(df_t['date'], errors='coerce').dt.normalize()
    df_p['date'] = pd.to_datetime(df_p['date'], errors='coerce').dt.normalize()
    df_t = df_t.dropna(subset=['date'])
    df_p = df_p.dropna(subset=['date'])
    
    df_full = df_t.merge(df_m, on='isin', how='left')
    return df_t, df_m, df_p, df_full