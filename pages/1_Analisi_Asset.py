import streamlit as st
import pandas as pd
import plotly.express as px
from utils import get_data, make_sidebar, style_chart_for_mobile

st.set_page_config(page_title="Analisi Asset", page_icon="🔎", layout="wide")
make_sidebar()
# Recupera ticker dalla sessione
ticker = st.session_state.get('selected_ticker')

if not ticker:
    st.warning("⚠️ Nessun asset selezionato.")
    st.info("Vai alla **Home**, seleziona una riga dalla tabella e verrai reindirizzato qui.")
    if st.button("Torna alla Home"):
        st.switch_page("app.py")
    st.stop()

if st.button("⬅️ Torna alla Dashboard"):
    st.switch_page("app.py")

st.title(f"🔎 Analisi: {ticker}")

# Carica dati
df_trans = get_data("transactions")
df_map = get_data("mapping")
df_prices = get_data("prices")

df_trans['date'] = pd.to_datetime(df_trans['date'], errors='coerce').dt.normalize()
df_prices['date'] = pd.to_datetime(df_prices['date'], errors='coerce').dt.normalize()

# Filtra dati
df_full = df_trans.merge(df_map, on='isin', how='left')
df_asset = df_full[df_full['ticker'] == ticker].sort_values('date', ascending=False)
asset_prices = df_prices[df_prices['ticker'] == ticker].sort_values('date')

# KPI Asset
qty = df_asset['quantity'].sum()
invested = -df_asset['local_value'].sum()
last_price = asset_prices.iloc[-1]['close_price'] if not asset_prices.empty else 0
curr_val = qty * last_price
pnl = curr_val - invested

c1, c2, c3, c4 = st.columns(4)
c1.metric("Quantità", f"{qty:.2f}")
c2.metric("Prezzo Oggi", f"€ {last_price:.2f}")
c3.metric("Valore", f"€ {curr_val:,.2f}")
c4.metric("P&L", f"€ {pnl:,.2f}", delta=f"{(pnl/invested)*100:.2f}%" if invested else "0%")

st.divider()

# Grafico Prezzo
if not asset_prices.empty:
    st.subheader("📉 Storico Prezzo")
    fig = px.line(asset_prices, x='date', y='close_price', title=f"Andamento {ticker}")
    fig.update_traces(line_color='#00CC96')
    fig = style_chart_for_mobile(fig) # APPLICA STILE
    st.plotly_chart(fig, use_container_width=True)

# Tabella Transazioni
st.subheader("📝 Storico Transazioni")
st.dataframe(
    df_asset[['date', 'product', 'quantity', 'local_value', 'fees']].style.format({
        'quantity': "{:.2f}", 'local_value': "€ {:.2f}", 'fees': "€ {:.2f}", 'date': lambda x: x.strftime('%d-%m-%Y')
    }),
    use_container_width=True,
    hide_index=True
)