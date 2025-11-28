import streamlit as st
import pandas as pd
import yfinance as yf
import hashlib
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, date

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Portfolio Manager", layout="wide", page_icon="📈")

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
    except:
        return pd.DataFrame()

def save_data(df, sheet_name):
    client = get_google_sheet_client()
    try:
        sh = client.open("PortfolioDB")
        try:
            wks = sh.worksheet(sheet_name)
        except:
            wks = sh.add_worksheet(title=sheet_name, rows=1000, cols=20)
        
        wks.clear()
        if not df.empty:
            df_str = df.astype(str)
            wks.update([df_str.columns.values.tolist()] + df_str.values.tolist())
    except Exception as e:
        st.error(f"Errore salvataggio {sheet_name}: {e}")

# --- PARSING ---
def parse_degiro_csv(file):
    df = pd.read_csv(file)
    cols = ['Quantità', 'Quotazione', 'Valore', 'Costi di transazione']
    for c in cols:
        if c in df.columns:
            df[c] = df[c].astype(str).str.replace(',', '.').apply(pd.to_numeric, errors='coerce').fillna(0)
    
    if 'Data' in df.columns:
        # FIX 1: Normalizzazione immediata all'importazione
        df['Data'] = pd.to_datetime(df['Data'], format='%d-%m-%Y', errors='coerce').dt.normalize()
    
    if 'Costi di transazione' in df.columns:
        df['Costi di transazione'] = df['Costi di transazione'].abs()
    return df

def generate_id(row):
    # Usa stringa della data per ID stabile
    d_str = row['Data'].strftime('%Y-%m-%d') if pd.notna(row['Data']) else ""
    raw = f"{d_str}{row['Ora']}{row['ISIN']}{row['ID Ordine']}"
    return hashlib.md5(raw.encode()).hexdigest()

def sync_prices(tickers):
    if not tickers: return 0
    df_prices = get_data("prices")
    
    # FIX 2: Pulizia date nel DB prezzi esistente
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
                # Scarica solo se mancano dati da ieri in poi
                if pd.notna(last) and last.date() < (date.today() - timedelta(days=1)):
                    start_date = (last + timedelta(days=1)).strftime('%Y-%m-%d')
                elif pd.notna(last):
                    # Già aggiornato
                    bar.progress((i+1)/len(tickers))
                    continue

        try:
            hist = yf.download(t, start=start_date, progress=False)
            if not hist.empty:
                closes = hist['Close']
                if isinstance(closes, pd.DataFrame): closes = closes.iloc[:,0]
                for d, v in closes.items():
                    if pd.notna(v):
                        # Salviamo data pulita
                        new_data.append({'ticker': t, 'date': d.strftime('%Y-%m-%d'), 'close_price': float(v)})
        except: pass
        bar.progress((i+1)/len(tickers))
    
    bar.empty()
    if new_data:
        df_new = pd.DataFrame(new_data)
        # Assicuriamoci che anche i nuovi siano datetime per il concat corretto
        df_new['date'] = pd.to_datetime(df_new['date'])
        
        # Unione sicura
        df_fin = pd.concat([df_prices, df_new], ignore_index=True)
        df_fin = df_fin.drop_duplicates(subset=['ticker', 'date'])
        
        # Salvataggio
        save_data(df_fin, "prices")
        return len(new_data)
    return 0

# --- MAIN ---
def main():
    st.title("🌐 Portfolio Cloud")
    
    with st.spinner("Caricamento Database..."):
        df_trans = get_data("transactions")
        df_map = get_data("mapping")
        df_prices = get_data("prices")

    # --- SIDEBAR ---
    with st.sidebar:
        st.header("Menu")
        up = st.file_uploader("CSV Degiro", type=['csv'])
        if up and st.button("Importa"):
            ndf = parse_degiro_csv(up)
            rows = []
            exist = df_trans['id'].tolist() if not df_trans.empty else []
            c = 0
            for _, r in ndf.iterrows():
                if pd.isna(r['ISIN']): continue
                tid = generate_id(r)
                if tid not in exist:
                    rows.append({
                        'id': tid, 'date': r['Data'].strftime('%Y-%m-%d'),
                        'product': r['Prodotto'], 'isin': r['ISIN'],
                        'quantity': r['Quantità'], 'local_value': r['Valore'],
                        'fees': r['Costi di transazione'], 'currency': 'EUR'
                    })
                    exist.append(tid)
                    c += 1
            if rows:
                save_data(pd.concat([df_trans, pd.DataFrame(rows)], ignore_index=True), "transactions")
                st.success(f"Aggiunte {c} righe")
                st.rerun()

    # --- SYNC BUTTON ---
    if not df_map.empty:
        if st.button("🔄 Aggiorna Prezzi"):
            sync_prices(df_map['ticker'].unique().tolist())
            st.rerun()

    # --- PULIZIA DATI CRITICA PER IL GRAFICO ---
    # Se mancano dati, stop
    if df_trans.empty or df_prices.empty or df_map.empty:
        st.info("Dati insufficienti per il grafico. Carica CSV e Aggiorna Prezzi.")
        return

    # FIX 3: Convertiamo TUTTE le date in formato 'datetime' puro (senza ora)
    df_trans['date'] = pd.to_datetime(df_trans['date'], errors='coerce').dt.normalize()
    df_prices['date'] = pd.to_datetime(df_prices['date'], errors='coerce').dt.normalize()
    
    # Rimuoviamo righe con date non valide
    df_trans = df_trans.dropna(subset=['date'])
    df_prices = df_prices.dropna(subset=['date'])
    
    # Merge Transazioni + Mapping
    df_full = df_trans.merge(df_map, on='isin', how='left')

    # --- CALCOLI ATTUALI ---
    last_p = df_prices.sort_values('date').groupby('ticker').tail(1).set_index('ticker')['close_price']
    
    view = df_full.groupby(['product', 'ticker']).agg({'quantity':'sum', 'local_value':'sum'}).reset_index()
    view = view[view['quantity'] > 0.001]
    view['net_invested'] = -view['local_value']
    view['curr_price'] = view['ticker'].map(last_p)
    view['mkt_val'] = view['quantity'] * view['curr_price']
    view['pnl'] = view['mkt_val'] - view['net_invested']
    
    # --- DASHBOARD KPI ---
    tot_val = view['mkt_val'].sum()
    tot_inv = view['net_invested'].sum()
    st.metric("Valore Portafoglio", f"€ {tot_val:,.2f}", delta=f"Investito: € {tot_inv:,.2f}")
    
    # --- LOGICA GRAFICO (Il cuore del problema) ---
    st.subheader("Andamento Temporale")
    
    # Creiamo la tabella pivot dei prezzi: Righe=Date, Colonne=Ticker
    # FIX 4: .sort_index() e .ffill() sono vitali per riempire i buchi dei weekend
    pivot = df_prices.pivot(index='date', columns='ticker', values='close_price').sort_index().ffill()
    
    # Assicuriamoci che l'indice della pivot sia datetime
    pivot.index = pd.to_datetime(pivot.index)

    # Generiamo tutte le date dal primo acquisto a oggi
    start_dt = df_trans['date'].min()
    rng = pd.date_range(start_dt, datetime.today(), freq='D').normalize()
    
    hist = []
    current_qty = {}
    
    # Raggruppiamo transazioni per data
    trans_grouped = df_full.groupby('date')
    
    for d in rng:
        # Aggiorna quantità se ci sono movimenti oggi
        if d in trans_grouped.groups:
            daily_moves = trans_grouped.get_group(d)
            for _, row in daily_moves.iterrows():
                tk = row['ticker']
                if pd.notna(tk):
                    current_qty[tk] = current_qty.get(tk, 0) + row['quantity']
        
        # Calcola valore totale del giorno 'd'
        day_val = 0
        for tk, qty in current_qty.items():
            if qty > 0 and tk in pivot.columns:
                # Trova il prezzo alla data 'd' o il più recente prima (asof)
                # Questo risolve il problema se 'd' è domenica
                if d >= pivot.index.min():
                    try:
                        idx = pivot.index.asof(d)
                        if pd.notna(idx):
                            price = pivot.at[idx, tk]
                            if pd.notna(price):
                                day_val += qty * price
                    except: pass
        
        hist.append({'Data': d, 'Valore': day_val})
    
    # Disegna
    chart_df = pd.DataFrame(hist)
    st.plotly_chart(px.line(chart_df, x='Data', y='Valore'), use_container_width=True)

    # --- TABELLA DETTAGLI ---
    st.subheader("Dettaglio")
    fmt = {'quantity':"{:.2f}", 'net_invested':"€ {:.2f}", 'mkt_val':"€ {:.2f}"}
    st.dataframe(view[['product', 'quantity', 'net_invested', 'mkt_val']].style.format(fmt))

if __name__ == "__main__":
    main()