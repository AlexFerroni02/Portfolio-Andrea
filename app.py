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

# --- CONNESSIONE GOOGLE SHEETS ---
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
    except Exception:
        return pd.DataFrame()

def save_data(df, sheet_name):
    client = get_google_sheet_client()
    sh = client.open("PortfolioDB")
    try:
        wks = sh.worksheet(sheet_name)
    except:
        wks = sh.add_worksheet(title=sheet_name, rows=1000, cols=20)
    
    wks.clear()
    if not df.empty:
        df_str = df.astype(str)
        wks.update([df_str.columns.values.tolist()] + df_str.values.tolist())

# --- FUNZIONI DI CALCOLO ---
def parse_degiro_csv(file):
    df = pd.read_csv(file)
    cols = ['Quantità', 'Quotazione', 'Valore', 'Costi di transazione']
    for c in cols:
        if c in df.columns:
            df[c] = df[c].astype(str).str.replace(',', '.').apply(pd.to_numeric, errors='coerce').fillna(0)
    
    if 'Data' in df.columns:
        df['Data'] = pd.to_datetime(df['Data'], format='%d-%m-%Y', errors='coerce')
    
    if 'Costi di transazione' in df.columns:
        df['Costi di transazione'] = df['Costi di transazione'].abs()
        
    return df

def generate_id(row):
    raw = f"{row['Data']}{row['Ora']}{row['ISIN']}{row['ID Ordine']}"
    return hashlib.md5(raw.encode()).hexdigest()

def sync_prices(tickers):
    """Scarica e salva i prezzi mancanti - VERSIONE PROTETTA"""
    if not tickers: return 0
    
    df_prices = get_data("prices")
    
    # --- PROTEZIONE ERRORI DATE ---
    if not df_prices.empty:
        # Se c'è sporcizia, la ignora (coerce) e rimuove le righe vuote
        df_prices['date'] = pd.to_datetime(df_prices['date'], errors='coerce')
        df_prices = df_prices.dropna(subset=['date'])
        
        # Converte anche il prezzo per sicurezza
        df_prices['close_price'] = pd.to_numeric(df_prices['close_price'], errors='coerce')
    
    new_data = []
    progress = st.progress(0)
    status = st.empty()
    
    for i, t in enumerate(tickers):
        status.write(f"Controllo {t}...")
        start_date = "2020-01-01"
        
        if not df_prices.empty:
            existing = df_prices[df_prices['ticker'] == t]
            if not existing.empty:
                last_date = existing['date'].max()
                if pd.notna(last_date):
                    if last_date.date() >= date.today():
                        continue
                    start_date = (last_date + timedelta(days=1)).strftime('%Y-%m-%d')
        
        try:
            hist = yf.download(t, start=start_date, progress=False)
            if not hist.empty:
                closes = hist['Close']
                if isinstance(closes, pd.DataFrame):
                    closes = closes.iloc[:, 0]
                
                for d, val in closes.items():
                    if pd.notna(val):
                        new_data.append({
                            'ticker': t,
                            'date': d.strftime('%Y-%m-%d'),
                            'close_price': float(val)
                        })
        except:
            pass
        progress.progress((i+1)/len(tickers))
        
    status.empty()
    progress.empty()
    
    if new_data:
        df_new = pd.DataFrame(new_data)
        # Unisce e rimuove duplicati
        df_final = pd.concat([df_prices, df_new], ignore_index=True)
        df_final = df_final.drop_duplicates(subset=['ticker', 'date'])
        save_data(df_final, "prices")
        return len(new_data)
    return 0

# --- INTERFACCIA UTENTE ---
def main():
    st.title("🌐 Il Mio Portafoglio Cloud")
    
    with st.spinner("Lettura Database..."):
        df_trans = get_data("transactions")
        df_map = get_data("mapping")

    # --- UPLOAD ---
    with st.sidebar:
        st.header("Gestione")
        up_file = st.file_uploader("Carica CSV Degiro", type=['csv'])
        if up_file and st.button("Importa"):
            new_df = parse_degiro_csv(up_file)
            rows = []
            exist_ids = df_trans['id'].tolist() if not df_trans.empty else []
            
            count = 0
            for _, r in new_df.iterrows():
                if pd.isna(r['ISIN']): continue
                tid = generate_id(r)
                if tid not in exist_ids:
                    rows.append({
                        'id': tid,
                        'date': r['Data'].strftime('%Y-%m-%d'),
                        'product': r['Prodotto'],
                        'isin': r['ISIN'],
                        'quantity': r['Quantità'],
                        'local_value': r['Valore'], 
                        'fees': r['Costi di transazione'],
                        'currency': 'EUR'
                    })
                    exist_ids.append(tid)
                    count += 1
            
            if rows:
                df_add = pd.DataFrame(rows)
                df_tot = pd.concat([df_trans, df_add], ignore_index=True)
                save_data(df_tot, "transactions")
                st.success(f"Aggiunte {count} transazioni!")
                st.rerun()
            else:
                st.info("Nessuna nuova transazione.")

    # --- AGGIORNA PREZZI ---
    if not df_map.empty:
        col1, col2 = st.columns([1,3])
        if col1.button("🔄 Aggiorna Prezzi"):
            tks = df_map['ticker'].unique().tolist()
            with st.spinner("Scaricamento dati da Yahoo..."):
                n = sync_prices(tks)
            if n > 0: st.success(f"Scaricati {n} nuovi prezzi!")
            else: st.info("Prezzi già aggiornati.")

    # --- DASHBOARD ---
    df_prices = get_data("prices")
    
    # PROTEZIONE DATE ANCHE QUI
    if not df_prices.empty:
        df_prices['date'] = pd.to_datetime(df_prices['date'], errors='coerce')
        df_prices = df_prices.dropna(subset=['date'])

    if not df_trans.empty and not df_map.empty and not df_prices.empty:
        df_full = df_trans.merge(df_map, on='isin', how='left')
        
        last_prices = df_prices.sort_values('date').groupby('ticker').tail(1).set_index('ticker')['close_price']
        
        view = df_full.groupby(['product', 'ticker']).agg({
            'quantity': 'sum',
            'local_value': 'sum'
        }).reset_index()
        
        view = view[view['quantity'] > 0.001]
        view['net_invested'] = -view['local_value']
        view['current_price'] = view['ticker'].map(last_prices)
        view['market_value'] = view['quantity'] * view['current_price']
        view['pnl'] = view['market_value'] - view['net_invested']
        view['pnl_perc'] = (view['pnl'] / view['net_invested']) * 100
        
        tot_mkt = view['market_value'].sum()
        tot_inv = view['net_invested'].sum()
        delta_val = tot_mkt - tot_inv
        
        k1, k2, k3 = st.columns(3)
        k1.metric("Valore Portafoglio", f"€ {tot_mkt:,.2f}")
        k2.metric("Capitale Investito", f"€ {tot_inv:,.2f}")
        k3.metric("Profitto/Perdita", f"€ {delta_val:,.2f}", 
                  delta=f"{(delta_val/tot_inv)*100:.2f}%" if tot_inv else "0%")
        
        st.divider()
        
        st.subheader("Andamento Temporale")
        df_trans['date'] = pd.to_datetime(df_trans['date'])
        pivot_p = df_prices.pivot(index='date', columns='ticker', values='close_price').ffill()
        
        start = df_trans['date'].min()
        rng = pd.date_range(start, datetime.today(), freq='D')
        
        history = []
        curr_q = {}
        trans_g = df_full.groupby('date')
        
        for d in rng:
            if d in trans_g.groups:
                for _, t in trans_g.get_group(d).iterrows():
                    tk = t['ticker']
                    if pd.notna(tk):
                        curr_q[tk] = curr_q.get(tk, 0) + t['quantity']
            
            val_day = 0
            for tk, q in curr_q.items():
                if q > 0 and tk in pivot_p.columns:
                    idx = pivot_p.index.asof(d)
                    if pd.notna(idx):
                        p = pivot_p.at[idx, tk]
                        if pd.notna(p):
                            val_day += q * p
            history.append({'Data': d, 'Valore': val_day})
            
        st.plotly_chart(px.line(pd.DataFrame(history), x='Data', y='Valore'), use_container_width=True)
        st.subheader("Dettaglio Asset")
        st.dataframe(view[['product', 'quantity', 'net_invested', 'market_value', 'pnl_perc']].style.format("{:.2f}"))

if __name__ == "__main__":
    main()