import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
from utils import load_and_clean_data

st.set_page_config(page_title="Portfolio Home", layout="wide", page_icon="🏠")

st.title("🏠 Dashboard Portafoglio")

# Carica dati
df_trans, df_map, df_prices, df_full = load_and_clean_data()

# Controllo se mancano dati
if df_full is None:
    st.info("👋 Benvenuto! Il database è vuoto.")
    st.warning("Vai alla pagina '📂 Gestione Dati' nel menu a sinistra per caricare il tuo primo CSV.")
    st.stop()

# Controllo se mancano mapping (e avvisa l'utente)
all_isins = df_trans['isin'].unique()
mapped_isins = df_map['isin'].unique()
missing = [i for i in all_isins if i not in mapped_isins]
if missing:
    st.error(f"⚠️ Attenzione: {len(missing)} ETF non hanno ancora un Ticker.")
    st.markdown("Vai su **Gestione Dati** per inserirli manualmente, altrimenti i calcoli saranno incompleti.")

# --- CALCOLI (Identici a prima) ---
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
c2.metric("💳 Capitale Investito", f"€ {tot_inv:,.2f}")
c3.metric("📈 Profitto Netto", f"€ {tot_pnl:,.2f}", delta=f"{(tot_pnl/tot_inv)*100:.2f}%" if tot_inv else "0%")

st.divider()

# --- GRAFICO STORICO ---
st.subheader("📊 Andamento Portafoglio")

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

    day_mkt_val = 0
    for tk, qty in current_qty.items():
        if qty > 0.001 and tk in pivot.columns:
            if d >= pivot.index.min():
                try:
                    idx = pivot.index.asof(d)
                    if pd.notna(idx):
                        price = pivot.at[idx, tk]
                        if pd.notna(price): day_mkt_val += qty * price
                except: pass
    
    hist.append({'Data': d, 'Valore': day_mkt_val, 'Spesa': cumulative_invested})

df_hist = pd.DataFrame(hist)
fig = go.Figure()
fig.add_trace(go.Scatter(x=df_hist['Data'], y=df_hist['Valore'], mode='lines', name='Valore', line=dict(color='#00CC96'), fill='tozeroy'))
fig.add_trace(go.Scatter(x=df_hist['Data'], y=df_hist['Spesa'], mode='lines', name='Costi', line=dict(color='#EF553B', dash='dash')))
st.plotly_chart(fig, use_container_width=True)