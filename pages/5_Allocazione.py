import streamlit as st
import pandas as pd
import plotly.express as px
import json

from utils import get_data, save_data, make_sidebar, fetch_justetf_allocation_json, save_allocation_json, style_chart_for_mobile

st.set_page_config(page_title="X-Ray Portafoglio", layout="wide", page_icon="🌍")
make_sidebar()
st.title("🌍 X-Ray Portafoglio")

# 1. Caricamento Dati
df_map = get_data("mapping")
df_alloc = get_data("asset_allocation")
df_trans = get_data("transactions")
df_prices = get_data("prices")

if df_map.empty or df_trans.empty:
    st.error("Dati mancanti. Vai a 'Gestione Dati' per importare transazioni e mappare i ticker.")
    st.stop()

# Calcolo valore attuale
if not df_prices.empty:
    df_prices['date'] = pd.to_datetime(df_prices['date'])
    last_p = df_prices.sort_values('date').groupby('ticker').tail(1).set_index('ticker')['close_price']
else:
    last_p = pd.Series(dtype='object')

df_full = df_trans.merge(df_map, on='isin', how='left')
holdings = df_full.groupby(['product', 'ticker', 'isin']).agg({'quantity':'sum'}).reset_index()

# Filtra per mostrare solo gli asset attualmente posseduti
view = holdings[holdings['quantity'] > 0.001].copy()
view['value'] = view['quantity'] * view['ticker'].map(last_p).fillna(0)

# Merge con dati allocazione (JSON)
if not df_alloc.empty:
    view = view.merge(df_alloc, on='ticker', how='left')

# --- CONFIGURATORE ---
with st.expander("🛠️ Scarica Dati di Allocazione per un Asset", expanded=True):
    col_sel, col_btn = st.columns([3, 1])
    with col_sel:
        options = view.apply(lambda x: f"{x['product']} ({x['ticker']})", axis=1).unique()
        selected_option = st.selectbox("Seleziona Asset:", options)
        sel_ticker = selected_option.split('(')[-1].replace(')', '')
        sel_isin = view[view['ticker'] == sel_ticker].iloc[0]['isin']
    
    with col_btn:
        st.write("")
        st.write("")
        if st.button("⚡ SCARICA DATI (JustETF)", type="primary"):
            with st.spinner(f"Analisi JustETF per {sel_ticker}..."):
                geo, sec = fetch_justetf_allocation_json(sel_isin)
                if geo or sec:
                    save_allocation_json(sel_ticker, geo, sec)
                    st.success(f"Dati per {sel_ticker} salvati! Trovati: {len(geo)} Paesi, {len(sec)} Settori.")
                    st.rerun()
                else:
                    st.error("Nessun dato di allocazione trovato automaticamente per questo ISIN.")

# --- ANALISI AGGREGATA ---
st.divider()
st.subheader("📊 Esposizione Totale del Portafoglio (Pesata)")

total_val = view['value'].sum()

if total_val > 0:
    total_geo = {}
    total_sec = {}
    
    for _, row in view.iterrows():
        val_etf = row['value']
        if val_etf == 0: continue

        try:
            geo_raw = row.get('geography_json', '{}')
            sec_raw = row.get('sector_json', '{}')
            g_map = geo_raw if isinstance(geo_raw, dict) else json.loads(geo_raw or '{}')
            s_map = sec_raw if isinstance(sec_raw, dict) else json.loads(sec_raw or '{}')
        except (json.JSONDecodeError, TypeError):
            g_map, s_map = {}, {}
        
        for country, perc in g_map.items():
            euro_exposure = val_etf * (float(perc) / 100)
            total_geo[country] = total_geo.get(country, 0) + euro_exposure
            
        for sector, perc in s_map.items():
            euro_exposure = val_etf * (float(perc) / 100)
            total_sec[sector] = total_sec.get(sector, 0) + euro_exposure

    c_geo, c_sec = st.columns(2)
    
    with c_geo:
        if total_geo:
            df_g = pd.DataFrame(list(total_geo.items()), columns=['Paese', 'Valore'])
            fig1 = px.pie(df_g, values='Valore', names='Paese', hole=0.4, title="Esposizione Geografica Totale")
            fig1 = style_chart_for_mobile(fig1)
            fig1.update_traces(textinfo='percent', hovertemplate='<b>%{label}</b><br>€%{value:,.0f}<br>%{percent}<extra></extra>')
            fig1.update_layout(showlegend=False)
            st.plotly_chart(fig1, use_container_width=True)
        else:
            st.info("Nessun dato geografico aggregato. Scarica i dati per i tuoi asset.")

    with c_sec:
        if total_sec:
            df_s = pd.DataFrame(list(total_sec.items()), columns=['Settore', 'Valore'])
            fig2 = px.pie(df_s, values='Valore', names='Settore', hole=0.4, title="Esposizione Settoriale Totale")
            fig2 = style_chart_for_mobile(fig2)
            fig2.update_traces(textinfo='percent', hovertemplate='<b>%{label}</b><br>€%{value:,.0f}<br>%{percent}<extra></extra>')
            fig2.update_layout(showlegend=False)
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Nessun dato settoriale aggregato.")
else:
    st.warning("Il valore del portafoglio è zero o i prezzi non sono aggiornati. Sincronizza i prezzi in 'Gestione Dati'.")