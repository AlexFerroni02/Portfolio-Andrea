import streamlit as st
import pandas as pd
import yfinance as yf
import hashlib
import plotly.express as px
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, date

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Portfolio Manager", layout="wide", page_icon="📈")

# --- CONNESSIONE GOOGLE SHEETS ---
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
        st.error(f"Errore Configurazione Secrets: {e}")
        return None

def get_data(sheet_name):
    client = get_google_sheet_client()
    if not client: return pd.DataFrame()
    
    try:
        sh = client.open("PortfolioDB")
        # Prova ad aprire il foglio
        try:
            wks = sh.worksheet(sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            # Se non esiste, crealo vuoto
            wks = sh.add_worksheet(title=sheet_name, rows=1000, cols=20)
            return pd.DataFrame()
            
        data = wks.get_all_records()
        return pd.DataFrame(data)
        
    except Exception as e:
        st.error(f"Errore accesso DB ({sheet_name}): {e}")
        return pd.DataFrame()

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
    except Exception as e:
        st.error(f"Errore salvataggio {sheet_name}: {e}")

# --- PARSING ---
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
    raw = f"{index}{d_str}{row['Ora']}{row['ISIN']}{row.get('ID Ordine','')}{row['Quantità']}{row['Valore']}"
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
        df_fin = pd.concat([df_prices, df_new], ignore_index=True).drop_duplicates(subset=['ticker', 'date'])
        save_data(df_fin, "prices")
        return len(new_data)
    return 0

def color_pnl(val):
    try:
        v = float(val.strip('%'))
        color = '#d4edda' if v >= 0 else '#f8d7da'
        text_color = '#155724' if v >= 0 else '#721c24'
        return f'background-color: {color}; color: {text_color}'
    except: return ''

# --- MAIN APP ---
def main():
    st.title("🌐 Portfolio Cloud")
    
    # 1. CARICAMENTO DATI (Con debug errori visibile)
    df_trans = get_data("transactions")
    df_map = get_data("mapping")
    df_prices = get_data("prices")

    # --- SIDEBAR ---
    with st.sidebar:
        st.header("1. Importa CSV")
        up = st.file_uploader("Carica Transactions.csv", type=['csv'])
        if up and st.button("Importa"):
            ndf = parse_degiro_csv(up)
            rows = []
            exist = df_trans['id'].tolist() if not df_trans.empty else []
            c = 0
            for idx, r in ndf.iterrows():
                if pd.isna(r['ISIN']): continue
                tid = generate_id(r, idx)
                if tid not in exist:
                    val = r['Totale'] if r['Totale'] != 0 else r['Valore']
                    rows.append({
                        'id': tid, 'date': r['Data'].strftime('%Y-%m-%d'),
                        'product': r['Prodotto'], 'isin': r['ISIN'],
                        'quantity': r['Quantità'], 'local_value': val,
                        'fees': r['Costi di transazione'], 'currency': 'EUR'
                    })
                    exist.append(tid)
                    c += 1
            if rows:
                new_df = pd.concat([df_trans, pd.DataFrame(rows)], ignore_index=True)
                save_data(new_df, "transactions")
                st.success(f"✅ Importate {c} righe.")
                st.rerun()
        
        st.divider()
        st.header("2. Aggiorna Prezzi")
        if not df_map.empty:
            if st.button("🔄 Scarica da Yahoo"):
                with st.spinner("Scaricamento..."):
                    n = sync_prices(df_map['ticker'].unique().tolist())
                st.success(f"Aggiornati {n} prezzi.")
                st.rerun() # Ricarica per vedere il grafico aggiornato
        else:
            st.warning("Mapping vuoto.")

    # --- 2. CONTROLLO ERRORI E MAPPING ---
    
    # Se il DB è vuoto, fermati e dillo chiaramente
    if df_trans.empty:
        st.info("👋 Il database 'transactions' risulta vuoto.")
        st.write("Se sei sicuro che il file Google Sheets contenga dati, controlla che il nome del foglio sia esattamente **transactions** (minuscolo).")
        st.stop()

    # Se mancano i mapping, chiedili
    all_isins = df_trans['isin'].unique()
    mapped_isins = df_map['isin'].unique() if not df_map.empty else []
    missing = [i for i in all_isins if i not in mapped_isins]
    
    if missing:
        st.warning(f"⚠️ Trovati {len(missing)} ETF senza Ticker!")
        with st.form("map_form"):
            new_maps = []
            for m in missing:
                prod = df_trans[df_trans['isin']==m]['product'].iloc[0]
                col1, col2 = st.columns([3,1])
                col1.text(f"{prod}\n{m}")
                val = col2.text_input("Ticker Yahoo", key=m)
                if val: new_maps.append({'isin': m, 'ticker': val.strip()})
            if st.form_submit_button("Salva Mappatura"):
                if new_maps:
                    df_new = pd.DataFrame(new_maps)
                    df_final = pd.concat([df_map, df_new], ignore_index=True) if not df_map.empty else df_new
                    save_data(df_final, "mapping")
                    st.success("Salvato!")
                    st.rerun()
        st.stop()

    # Se mancano i prezzi, avvisa ma prova a mostrare quello che c'è
    if df_prices.empty:
        st.warning("⚠️ Non ci sono prezzi storici. Clicca 'Scarica da Yahoo' nel menu a sinistra.")

    # --- 3. DASHBOARD ---
    
    # Normalizzazione Date
    df_trans['date'] = pd.to_datetime(df_trans['date'], errors='coerce').dt.normalize()
    if not df_prices.empty:
        df_prices['date'] = pd.to_datetime(df_prices['date'], errors='coerce').dt.normalize()
        df_prices = df_prices.dropna(subset=['date'])
    
    df_trans = df_trans.dropna(subset=['date'])
    
    df_full = df_trans.merge(df_map, on='isin', how='left')

    # Calcoli
    if not df_prices.empty:
        last_p = df_prices.sort_values('date').groupby('ticker').tail(1).set_index('ticker')['close_price']
        view = df_full.groupby(['product', 'ticker']).agg({'quantity':'sum', 'local_value':'sum'}).reset_index()
        view = view[view['quantity'] > 0.001]
        
        view['net_invested'] = -view['local_value']
        view['curr_price'] = view['ticker'].map(last_p)
        view['mkt_val'] = view['quantity'] * view['curr_price']
        view['pnl'] = view['mkt_val'] - view['net_invested']
        view['pnl%'] = (view['pnl']/view['net_invested'])*100
        
        tot_val = view['mkt_val'].sum()
        tot_inv = view['net_invested'].sum()
        tot_pnl = tot_val - tot_inv
        
        c1, c2, c3 = st.columns(3)
        c1.metric("💰 Valore Attuale", f"€ {tot_val:,.2f}")
        c2.metric("💳 Investito (incl. Costi)", f"€ {tot_inv:,.2f}")
        c3.metric("📈 Profitto Netto", f"€ {tot_pnl:,.2f}", delta=f"{(tot_pnl/tot_inv)*100:.2f}%" if tot_inv else "0%")
        
        st.divider()
        
        # Grafico
        st.subheader("📊 Crescita del Capitale")
        pivot = df_prices.pivot(index='date', columns='ticker', values='close_price').sort_index().ffill()
        pivot.index = pd.to_datetime(pivot.index)
        
        start_dt = df_trans['date'].min()
        rng = pd.date_range(start_dt, datetime.today(), freq='D').normalize()
        
        hist = []
        current_qty = {}
        cumulative_invested = 0
        trans_grouped = df_full.groupby('date')
        
        for d in rng:
            if d in trans_grouped.groups:
                daily_moves = trans_grouped.get_group(d)
                for _, row in daily_moves.iterrows():
                    tk = row['ticker']
                    if pd.notna(tk):
                        current_qty[tk] = current_qty.get(tk, 0) + row['quantity']
                    cumulative_invested += (-row['local_value'])
            
            day_val = 0
            for tk, qty in current_qty.items():
                if qty > 0.001 and tk in pivot.columns:
                    if d >= pivot.index.min():
                        try:
                            idx = pivot.index.asof(d)
                            if pd.notna(idx):
                                price = pivot.at[idx, tk]
                                if pd.notna(price): day_val += qty * price
                        except: pass
            
            hist.append({'Data': d, 'Valore': day_val, 'Investito': cumulative_invested})
        
        df_hist = pd.DataFrame(hist)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_hist['Data'], y=df_hist['Valore'], mode='lines', name='Valore Portafoglio', line=dict(color='#00CC96'), fill='tozeroy'))
        fig.add_trace(go.Scatter(x=df_hist['Data'], y=df_hist['Investito'], mode='lines', name='Soldi Versati', line=dict(color='#EF553B', dash='dash')))
        fig.update_layout(hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)

        # Tabella
        st.subheader("📋 Dettaglio Asset")
        display_df = view[['product', 'quantity', 'net_invested', 'mkt_val', 'pnl%']].copy()
        format_dict = {'quantity': "{:.2f}", 'net_invested': "€ {:.2f}", 'mkt_val': "€ {:.2f}", 'pnl%': "{:.2f}"}
        st.dataframe(display_df.style.format(format_dict).applymap(color_pnl, subset=['pnl%']).format({'pnl%': "{:.2f}%"}))

if __name__ == "__main__":
    main()