import streamlit as st
import pandas as pd
import plotly.express as px
import json
from utils import get_data, make_sidebar, style_chart_for_mobile

st.set_page_config(page_title="Analisi Asset", page_icon="🔎", layout="wide")
make_sidebar()
st.title("🔎 Analisi per Singolo Asset")

# --- CARICAMENTO DATI ---
with st.spinner("Caricamento dati..."):
    df_trans = get_data("transactions")
    df_map = get_data("mapping")
    df_prices = get_data("prices")
    df_alloc = get_data("asset_allocation")

if df_trans.empty or df_map.empty:
    st.warning("⚠️ Dati di transazioni o mappatura mancanti.")
    st.info("Vai alla pagina 'Gestione Dati' per importare e configurare i tuoi asset.")
    st.stop()

# --- LOGICA PER OTTENERE LA LISTA DEGLI ASSET POSSEDUTI ---
df_full = df_trans.merge(df_map, on='isin', how='left')
holdings = df_full.groupby(['product', 'ticker', 'isin']).agg({'quantity':'sum'}).reset_index()
owned_assets = holdings[holdings['quantity'] > 0.001].copy()
asset_options = owned_assets.apply(lambda x: f"{x['product']} ({x['ticker']})", axis=1).tolist()

if not asset_options:
    st.info("Nessun asset attualmente in portafoglio.")
    st.stop()

# --- SELETTORE ASSET ---
# Determina l'asset di default: quello selezionato dalla home o il primo della lista
default_index = 0
if 'selected_ticker' in st.session_state:
    try:
        # Trova l'opzione che corrisponde al ticker salvato
        selected_option_str = next(opt for opt in asset_options if st.session_state.selected_ticker in opt)
        default_index = asset_options.index(selected_option_str)
    except StopIteration:
        pass # Se non lo trova, usa l'indice 0
    # Pulisci lo stato per non rimanere "bloccato" su questo asset
    del st.session_state['selected_ticker']

selected_asset_str = st.selectbox("Seleziona un asset da analizzare:", asset_options, index=default_index)
ticker = selected_asset_str.split('(')[-1].replace(')', '')

# --- FILTRA I DATI PER L'ASSET SELEZIONATO ---
df_asset_trans = df_full[df_full['ticker'] == ticker].sort_values('date', ascending=False)
asset_prices = df_prices[df_prices['ticker'] == ticker].sort_values('date') if not df_prices.empty else pd.DataFrame()
asset_info = owned_assets[owned_assets['ticker'] == ticker].iloc[0]

# --- HEADER CON INFO E PULSANTI ---
col_title, col_btn = st.columns([4, 1])
with col_title:
    st.header(f"{asset_info['product']}")
    st.caption(f"Ticker: **{ticker}** | ISIN: **{asset_info['isin']}**")
with col_btn:
    if 'ETF' in asset_info['product']:
        st.link_button("🔎 Vedi su JustETF", f"https://www.justetf.com/it/etf-profile.html?isin={asset_info['isin']}")

# --- KPI ASSET ---
qty = asset_info['quantity']
invested = -df_asset_trans['local_value'].sum()
last_price = asset_prices.iloc[-1]['close_price'] if not asset_prices.empty else 0
curr_val = qty * last_price
pnl = curr_val - invested

c1, c2, c3, c4 = st.columns(4)
c1.metric("Quantità", f"{qty:.2f}")
c2.metric("Prezzo Corrente", f"€ {last_price:.2f}")
c3.metric("Valore di Mercato", f"€ {curr_val:,.2f}")
c4.metric("P&L", f"€ {pnl:,.2f}", delta=f"{(pnl/invested)*100:.2f}%" if invested else "0%")
st.divider()

# --- GRAFICI ALLOCAZIONE ---
st.subheader("🔬 Composizione Asset")
asset_alloc_data = df_alloc[df_alloc['ticker'] == ticker] if not df_alloc.empty else pd.DataFrame()

if not asset_alloc_data.empty:
    geo_raw = asset_alloc_data.iloc[0].get('geography_json', '{}')
    sec_raw = asset_alloc_data.iloc[0].get('sector_json', '{}')
    try:
        geo_data = geo_raw if isinstance(geo_raw, dict) else json.loads(geo_raw or '{}')
        sec_data = sec_raw if isinstance(sec_raw, dict) else json.loads(sec_raw or '{}')
    except (json.JSONDecodeError, TypeError):
        geo_data, sec_data = {}, {}

    col1, col2 = st.columns(2)
    with col1:
        if geo_data:
            df_g = pd.DataFrame(list(geo_data.items()), columns=['Paese', 'Percentuale'])
            fig_geo = px.pie(df_g, values='Percentuale', names='Paese', title='Esposizione Geografica', hole=0.4)
            fig_geo.update_layout(showlegend=False)
            fig_geo.update_traces(textinfo='percent', textposition='inside', hovertemplate='<b>%{label}</b>: %{value:.2f}%<extra></extra>')
            st.plotly_chart(style_chart_for_mobile(fig_geo), use_container_width=True)
        else:
            st.info("Nessun dato geografico disponibile per questo asset.")
    with col2:
        if sec_data:
            df_s = pd.DataFrame(list(sec_data.items()), columns=['Settore', 'Percentuale'])
            fig_sec = px.pie(df_s, values='Percentuale', names='Settore', title='Esposizione Settoriale', hole=0.4)
            fig_sec.update_layout(showlegend=False)
            fig_sec.update_traces(textinfo='percent', textposition='inside', hovertemplate='<b>%{label}</b>: %{value:.2f}%<extra></extra>')
            st.plotly_chart(style_chart_for_mobile(fig_sec), use_container_width=True)
        else:
            st.info("Nessun dato settoriale disponibile per questo asset.")
else:
    st.info("Dati di allocazione non ancora scaricati. Vai su 'Gestione Dati' per scaricarli.")

# --- GRAFICO PREZZO E TABELLA TRANSAZIONI ---
st.divider()
if not asset_prices.empty:
    st.subheader("📉 Storico Prezzo")
    fig = px.line(asset_prices, x='date', y='close_price', title=f"Andamento {ticker}")
    fig.update_traces(line_color='#00CC96')
    fig = style_chart_for_mobile(fig)
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Nessuna informazione sullo storico prezzi per questo asset.")

st.subheader("📝 Storico Transazioni")
st.dataframe(
    df_asset_trans[['date', 'product', 'quantity', 'local_value', 'fees']].style.format({
        'quantity': "{:.2f}", 'local_value': "€ {:.2f}", 'fees': "€ {:.2f}", 'date': lambda x: x.strftime('%d-%m-%Y')
    }),
    use_container_width=True,
    hide_index=True
)