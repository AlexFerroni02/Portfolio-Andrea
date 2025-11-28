import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
from utils import load_and_clean_data

# Configurazione pagina
st.set_page_config(page_title="Portfolio Home", layout="wide", page_icon="🏠")

st.title("🏠 Dashboard Portafoglio")
st.sidebar.success("Menu Caricato Correttamente")
# --- MENU LATERALE MANUALE ---
# Qui definiamo esplicitamente i link alle pagine
with st.sidebar:
    st.header("Navigazione")
    # Link alla Home (questo file)
    st.page_link("app.py", label="Home", icon="🏠")
    
    # Link alle altre pagine (assicurati che i nomi dei file siano esatti)
    st.page_link("pages/1_Analisi_Asset.py", label="Analisi Asset", icon="🔎")
    st.page_link("pages/2_Gestione_Dati.py", label="Gestione Dati", icon="📂")
    
    st.divider()
    st.success("Menu Caricato")
# 1. Caricamento Dati
df_trans, df_map, df_prices, df_full = load_and_clean_data()

# Se mancano dati, avvisa
if df_full is None:
    st.info("👋 Benvenuto! Il database sembra vuoto.")
    st.warning("Per iniziare: apri il menu a sinistra (>) e vai su '📂 Gestione'.")
    st.stop()

# 2. Calcoli Snapshot (Oggi)
last_p = df_prices.sort_values('date').groupby('ticker').tail(1).set_index('ticker')['close_price']

view = df_full.groupby(['product', 'ticker']).agg({'quantity':'sum', 'local_value':'sum'}).reset_index()
view = view[view['quantity'] > 0.001] # Nasconde ETF venduti

view['net_invested'] = -view['local_value']
view['curr_price'] = view['ticker'].map(last_p)
view['mkt_val'] = view['quantity'] * view['curr_price']
view['pnl'] = view['mkt_val'] - view['net_invested']
view['pnl%'] = (view['pnl']/view['net_invested'])*100

# Totali Generali
tot_val = view['mkt_val'].sum()
tot_inv = view['net_invested'].sum()
tot_pnl = tot_val - tot_inv

# KPI in alto
c1, c2, c3 = st.columns(3)
c1.metric("💰 Valore Attuale", f"€ {tot_val:,.2f}")
c2.metric("💳 Investito (incl. Costi)", f"€ {tot_inv:,.2f}")
c3.metric("📈 Profitto Netto", f"€ {tot_pnl:,.2f}", delta=f"{(tot_pnl/tot_inv)*100:.2f}%" if tot_inv else "0%")

st.divider()

# 3. GRAFICO (Valore vs Costi)
st.subheader("📊 Andamento nel Tempo")

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
fig.update_layout(margin=dict(l=0, r=0, t=30, b=0), hovermode="x unified")
st.plotly_chart(fig, use_container_width=True)

st.divider()

# 4. TABELLA ASSET (Quella che ti mancava!)
st.subheader("📋 I Tuoi Asset")

# Funzione per colorare le percentuali
def color_pnl(val):
    try:
        v = float(val.strip('%'))
        color = '#d4edda' if v >= 0 else '#f8d7da' # Verde / Rosso
        text_color = '#155724' if v >= 0 else '#721c24'
        return f'background-color: {color}; color: {text_color}'
    except:
        return ''

# Prepariamo la tabella bella pulita
display_df = view[['product', 'quantity', 'net_invested', 'mkt_val', 'pnl%']].copy()
display_df = display_df.sort_values('mkt_val', ascending=False) # Ordina per valore (i più grandi in alto)

# Rinominiamo le colonne per renderle più leggibili
display_df.columns = ['Prodotto', 'Quote', 'Investito (€)', 'Valore (€)', 'P&L %']

format_dict = {
    'Quote': "{:.2f}",
    'Investito (€)': "€ {:.2f}",
    'Valore (€)': "€ {:.2f}",
    'P&L %': "{:.2f}" # Lasciamo numero puro per colorare
}

st.dataframe(
    display_df.style
    .format(format_dict)
    .applymap(color_pnl, subset=['P&L %'])
    .format({'P&L %': "{:.2f}%"}) # Aggiunge il % dopo aver colorato
)