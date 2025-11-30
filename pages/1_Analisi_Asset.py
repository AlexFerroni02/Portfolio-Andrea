import streamlit as st
import pandas as pd
import plotly.express as px
import json
from utils import get_data, make_sidebar, style_chart_for_mobile

st.set_page_config(page_title="Analisi Asset", page_icon="🔎", layout="wide")
make_sidebar()

ticker = st.session_state.get('selected_ticker')

if not ticker:
    st.warning("⚠️ Nessun asset selezionato.")
    st.info("Vai alla **Home**, seleziona una riga dalla tabella e verrai reindirizzato qui.")
    if st.button("Torna alla Home"):
        st.switch_page("app.py")
    st.stop()

# Carica dati
df_trans = get_data("transactions")
df_map = get_data("mapping")
df_prices = get_data("prices")
df_alloc = get_data("asset_allocation") # Carica i dati di allocazione

df_trans['date'] = pd.to_datetime(df_trans['date'], errors='coerce').dt.normalize()
df_prices['date'] = pd.to_datetime(df_prices['date'], errors='coerce').dt.normalize()

# Filtra dati
df_full = df_trans.merge(df_map, on='isin', how='left')
df_asset = df_full[df_full['ticker'] == ticker].sort_values('date', ascending=False)
asset_prices = df_prices[df_prices['ticker'] == ticker].sort_values('date')

# Ottieni informazioni aggiuntive sull'asset
asset_info = df_asset.iloc[0] if not df_asset.empty else None
product_name = asset_info['product'] if asset_info is not None else ticker
isin = asset_info['isin'] if asset_info is not None else None

# --- HEADER CON PULSANTI ---
col_title, col_btn1, col_btn2 = st.columns([3, 1, 1])
with col_title:
    st.title(f"🔎 {product_name}")
    st.caption(f"Ticker: **{ticker}** | ISIN: **{isin if isin else 'N/A'}**")
with col_btn1:
    if st.button("⬅️ Torna alla Dashboard"):
        st.switch_page("app.py")
with col_btn2:
    # Mostra il link a JustETF solo se è un ETF
    if isin and 'ETF' in product_name:
        justetf_url = f"https://www.justetf.com/it/etf-profile.html?isin={isin}#allocation"
        st.link_button("🔎 Vedi su JustETF", justetf_url)

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

# --- GRAFICI ALLOCAZIONE ---
st.subheader("🔬 Composizione Asset")
asset_alloc_data = df_alloc[df_alloc['ticker'] == ticker]

if not asset_alloc_data.empty:
    # --- FIX: Gestione robusta dei dati JSON/JSONB dal DB ---
    geo_raw = asset_alloc_data.iloc[0].get('geography_json', '{}')
    sec_raw = asset_alloc_data.iloc[0].get('sector_json', '{}')
    
    try:
        # Se il DB restituisce già un dizionario, usalo. Altrimenti, parsa la stringa.
        geo_data = geo_raw if isinstance(geo_raw, dict) else json.loads(geo_raw or '{}')
        sec_data = sec_raw if isinstance(sec_raw, dict) else json.loads(sec_raw or '{}')
    except (json.JSONDecodeError, TypeError):
        geo_data, sec_data = {}, {}

    col1, col2 = st.columns(2)
    with col1:
        if geo_data:
            df_g = pd.DataFrame(list(geo_data.items()), columns=['Paese', 'Percentuale'])
            fig_geo = px.pie(df_g, values='Percentuale', names='Paese', title='Esposizione Geografica')
            fig_geo.update_layout(showlegend=False)
            fig_geo.update_traces(textinfo='percent', textposition='inside', hovertemplate='<b>%{label}</b>: %{value:.2f}%<extra></extra>')
            st.plotly_chart(style_chart_for_mobile(fig_geo), use_container_width=True)
        else:
            st.info("Nessun dato geografico per questo asset. Vai su 'X-Ray Portafoglio' per scaricarlo.")
    
    with col2:
        if sec_data:
            df_s = pd.DataFrame(list(sec_data.items()), columns=['Settore', 'Percentuale'])
            fig_sec = px.pie(df_s, values='Percentuale', names='Settore', title='Esposizione Settoriale')
            fig_sec.update_layout(showlegend=False)
            fig_sec.update_traces(textinfo='percent', textposition='inside', hovertemplate='<b>%{label}</b>: %{value:.2f}%<extra></extra>')
            st.plotly_chart(style_chart_for_mobile(fig_sec), use_container_width=True)
        else:
            st.info("Nessun dato settoriale per questo asset. Vai su 'X-Ray Portafoglio' per scaricarlo.")
else:
    st.info("Dati di allocazione non ancora scaricati per questo asset. Vai alla pagina 'X-Ray Portafoglio'.")


# Grafico Prezzo
if not asset_prices.empty:
    st.subheader("📉 Storico Prezzo")
    fig = px.line(asset_prices, x='date', y='close_price', title=f"Andamento {ticker}")
    fig.update_traces(line_color='#00CC96')
    fig = style_chart_for_mobile(fig)
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