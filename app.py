import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import json
from utils import get_data, save_data, color_pnl, make_sidebar, style_chart_for_mobile

st.set_page_config(page_title="Portfolio Pro", layout="wide", page_icon="🚀")
make_sidebar()
st.title("🚀 Dashboard Portafoglio")

CATEGORIE_ASSET = ["Azionario", "Obbligazionario", "Gold", "Liquidità"]

with st.spinner("Caricamento dati..."):
    df_trans = get_data("transactions")
    df_map = get_data("mapping")
    df_prices = get_data("prices")
    df_settings = get_data("settings")
    df_budget = get_data("budget")
    df_alloc = get_data("asset_allocation")

if df_trans.empty:
    st.info("👋 Benvenuto! Il database è vuoto. Vai su 'Gestione Dati' per importare il CSV."), st.stop()

all_isins = df_trans['isin'].unique()
mapped_isins = df_map['isin'].unique() if not df_map.empty else []
missing_isins = [i for i in all_isins if i not in mapped_isins]

if missing_isins:
    st.warning(f"⚠️ Ci sono {len(missing_isins)} nuovi asset da mappare!")
    with st.form("quick_mapping_form"):
        new_mappings = []
        for isin in missing_isins:
            prod_name = df_trans[df_trans['isin'] == isin]['product'].iloc[0]
            st.write(f"**{prod_name}** ({isin})")
            col1, col2 = st.columns(2)
            ticker_input = col1.text_input("Ticker Yahoo", key=f"ticker_{isin}", placeholder="es. SWDA.MI")
            category_input = col2.selectbox("Categoria", CATEGORIE_ASSET, key=f"cat_{isin}")
            if ticker_input and category_input:
                new_mappings.append({'isin': isin, 'ticker': ticker_input.strip(), 'category': category_input})
            st.divider()
        if st.form_submit_button("💾 Salva e Aggiorna"):
            if new_mappings:
                new_df = pd.DataFrame(new_mappings)
                df_final = pd.concat([df_map, new_df], ignore_index=True).drop_duplicates(subset=['isin'], keep='last')
                save_data(df_final, "mapping")
                st.success("Mappatura salvata! Ricarico la pagina...")
                st.rerun()
    st.stop() 

df_trans['date'] = pd.to_datetime(df_trans['date'], errors='coerce').dt.normalize()
df_prices['date'] = pd.to_datetime(df_prices['date'], errors='coerce').dt.normalize()
if not df_budget.empty: df_budget['date'] = pd.to_datetime(df_budget['date'], errors='coerce').dt.normalize()

df_full = df_trans.merge(df_map, on='isin', how='left')
last_p = df_prices.sort_values('date').groupby('ticker').tail(1).set_index('ticker')['close_price']
view = df_full.groupby(['product', 'ticker', 'category']).agg({'quantity':'sum', 'local_value':'sum'}).reset_index()
view = view[view['quantity'] > 0.001] 
view['net_invested'] = -view['local_value']
view['curr_price'] = view['ticker'].map(last_p)
view['mkt_val'] = view['quantity'] * view['curr_price']
view['pnl'] = view['mkt_val'] - view['net_invested']
view['pnl%'] = (view['pnl'] / view['net_invested']) * 100

tot_val_assets = view['mkt_val'].sum()
tot_inv_assets = view['net_invested'].sum()
tot_pnl_assets = tot_val_assets - tot_inv_assets
c1, c2, c3 = st.columns(3)
c1.metric("💰 Valore Portafoglio Attuale", f"€ {tot_val_assets:,.2f}")
c2.metric("💳 Capitale Versato", f"€ {tot_inv_assets:,.2f}")
c3.metric("📈 P&L Netto", f"€ {tot_pnl_assets:,.2f}", delta=f"{(tot_pnl_assets/tot_inv_assets)*100:.2f}%" if tot_inv_assets else "0%")
st.divider()

final_liquidity, liquidity_label, manual_override = 0.0, "Liquidità", False
if not df_settings.empty:
    liquidity_setting = df_settings[df_settings['key'] == 'manual_liquidity']
    if not liquidity_setting.empty:
        manual_liquidity_value = float(liquidity_setting['value'].iloc[0])
        if manual_liquidity_value > 0:
            final_liquidity, liquidity_label, manual_override = manual_liquidity_value, "Liquidità Manuale", True
if not manual_override and not df_budget.empty and not df_trans.empty:
    start_date_budget = df_budget['date'].min()
    budget_since_start = df_budget[df_budget['date'] >= start_date_budget]
    trans_since_start = df_trans[df_trans['date'] >= start_date_budget]
    total_entrate = budget_since_start[budget_since_start['type'] == 'Entrata']['amount'].sum()
    total_uscite = budget_since_start[budget_since_start['type'] == 'Uscita']['amount'].sum()
    total_investito_netto = -trans_since_start['local_value'].sum()
    final_liquidity = total_entrate - total_uscite - total_investito_netto
    liquidity_label = "Liquidità Calcolata"
if final_liquidity > 0:
    liquidita_row = pd.DataFrame([{'product': liquidity_label, 'ticker': 'CASH', 'category': 'Liquidità', 'quantity': 1, 'local_value': 0, 'net_invested': final_liquidity, 'curr_price': final_liquidity, 'mkt_val': final_liquidity, 'pnl': 0, 'pnl%': 0}])
    view = pd.concat([view, liquidita_row], ignore_index=True)

st.subheader("🔬 Analisi Composizione Portafoglio")
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["Asset Class", "Azioni/Obbligazioni/Gold", "Tutti gli Asset", "Dettaglio Azionario", "Dettaglio Obbligazionario", "🌍 Allocazione (X-Ray)"])

with tab1:
    composition_data = view.groupby('category')['mkt_val'].sum().reset_index()
    color_map = {'Azionario': '#3B82F6', 'Obbligazionario': '#EF4444', 'Gold': '#D4AF37', 'Liquidità': '#10B981', 'Altro': '#9CA3AF'}
    fig_cat = px.pie(composition_data, values='mkt_val', names='category', title='Suddivisione per Asset Class', color='category', color_discrete_map=color_map)
    fig_cat = style_chart_for_mobile(fig_cat)
    fig_cat.update_traces(textinfo='percent+value', texttemplate='%{percent} <br>€%{value:,.0f}', hovertemplate='<b>%{label}</b><br>Valore: €%{value:,.2f}<br>(%{percent})<extra></extra>')
    st.plotly_chart(fig_cat, use_container_width=True)
with tab2:
    categories_to_show = ['Azionario', 'Obbligazionario', 'Gold']
    filtered_data = view[view['category'].isin(categories_to_show)]
    composition_data = filtered_data.groupby('category')['mkt_val'].sum().reset_index()
    color_map = {'Azionario': '#3B82F6', 'Obbligazionario': "#EF4444", 'Gold': '#D4AF37'}
    fig_simple = px.pie(composition_data, values='mkt_val', names='category', title='Ripartizione: Azioni / Obbligazioni / Gold', color='category', color_discrete_map=color_map)
    fig_simple = style_chart_for_mobile(fig_simple)
    fig_simple.update_traces(textinfo='percent+value', texttemplate='%{percent} <br>€%{value:,.0f}', hovertemplate='<b>%{label}</b><br>Valore: €%{value:,.2f}<br>(%{percent})<extra></extra>')
    st.plotly_chart(fig_simple, use_container_width=True)
with tab3:
    if not view.empty:
        # Colori fissi per categoria
        color_map = {'Azionario': '#3B82F6', 'Obbligazionario': '#EF4444', 'Gold': '#D4AF37', 'Liquidità': '#10B981', 'Altro': '#9CA3AF'}

        # Prepara i dati: prendi solo le colonne rilevanti e normalizza category
        prod_df = view[['product', 'category', 'mkt_val']].copy()
        prod_df['category'] = prod_df['category'].fillna('Altro').astype(str)

        # Mappa categorie sconosciute su 'Altro' così tutte hanno un colore noto
        prod_df['category'] = prod_df['category'].apply(lambda c: c if c in color_map else 'Altro')

        # Ordine desiderato per raggruppare i segmenti (così categorie vicine)
        desired_order = ['Azionario', 'Obbligazionario', 'Gold', 'Liquidità', 'Altro']
        prod_df['category'] = pd.Categorical(prod_df['category'], categories=desired_order, ordered=True)

        # Ordina per categoria (gruppa insieme) e poi per valore decrescente
        prod_df = prod_df.sort_values(['category', 'mkt_val'], ascending=[True, False]).reset_index(drop=True)

        # Rimuovi righe con valore 0 per evitare slice 0% nel grafico
        plot_df = prod_df[prod_df['mkt_val'] > 0].copy()

        if plot_df.empty:
            st.info("Nessun asset con valore da mostrare.")
        else:
            # Calcola percentuale e mostra etichetta solo se rilevante (evita etichette '0%')
            total = plot_df['mkt_val'].sum()
            plot_df = plot_df.copy()
            plot_df['pct'] = (plot_df['mkt_val'] / total) * 100
            plot_df['text'] = plot_df['pct'].apply(lambda x: f"{x:.1f}%" if x >= 0.5 else "")

            # Crea il grafico - usa color sulla colonna category (mappa fissa)
            fig_all_assets = px.pie(
                plot_df,
                values='mkt_val',
                names='product',
                title='Composizione per singolo Asset',
                color='category',
                color_discrete_map=color_map
            )
            fig_all_assets = style_chart_for_mobile(fig_all_assets)

            # Usa le percentuali calcolate come testo (evita 0%)
            fig_all_assets.update_traces(
                text=plot_df['text'],
                textinfo='text',
                hovertemplate='<b>%{label}</b><br>Valore: €%{value:,.2f}<br>(%{percent})<extra></extra>'
            )
            fig_all_assets.update_layout(showlegend=False)
            st.plotly_chart(fig_all_assets, use_container_width=True)
    else:
        st.info("Nessun asset in portafoglio.")
with tab4:
    df_azionario = view[view['category'] == 'Azionario']
    if not df_azionario.empty:
        fig_stock = px.pie(df_azionario, values='mkt_val', names='product', title='Composizione Portafoglio Azionario')
        fig_stock = style_chart_for_mobile(fig_stock)
        fig_stock.update_traces(textinfo='percent', hovertemplate='<b>%{label}</b><br>Valore: €%{value:,.2f}<br>(%{percent})<extra></extra>')
        fig_stock.update_layout(showlegend=False)
        st.plotly_chart(fig_stock, use_container_width=True)
    else: st.info("Nessun asset azionario in portafoglio.")
with tab5:
    df_obbligazionario = view[view['category'] == 'Obbligazionario']
    if not df_obbligazionario.empty:
        fig_bond = px.pie(df_obbligazionario, values='mkt_val', names='product', title='Composizione Portafoglio Obbligazionario')
        fig_bond = style_chart_for_mobile(fig_bond)
        fig_bond.update_traces(textinfo='percent', hovertemplate='<b>%{label}</b><br>Valore: €%{value:,.2f}<br>(%{percent})<extra></extra>')
        fig_bond.update_layout(showlegend=False)
        st.plotly_chart(fig_bond, use_container_width=True)
    else: st.info("Nessun asset obbligazionario in portafoglio.")
with tab6:
    st.caption("Questa analisi mostra l'esposizione geografica e settoriale aggregata, pesata per il valore di ogni asset. I dati sono basati sulle informazioni scaricate in 'Gestione Dati'.")
    view_alloc = view.copy()
    if not df_alloc.empty: view_alloc = view_alloc.merge(df_alloc, on='ticker', how='left')
    total_val = view_alloc['mkt_val'].sum()
    if total_val > 0:
        total_geo, total_sec = {}, {}
        for _, row in view_alloc.iterrows():
            val_etf = row['mkt_val']
            if val_etf == 0 or pd.isna(val_etf): continue
            try:
                geo_raw = row.get('geography_json', '{}')
                sec_raw = row.get('sector_json', '{}')
                g_map = geo_raw if isinstance(geo_raw, dict) else json.loads(geo_raw or '{}')
                s_map = sec_raw if isinstance(sec_raw, dict) else json.loads(sec_raw or '{}')
            except (json.JSONDecodeError, TypeError): g_map, s_map = {}, {}
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
            else: st.info("Nessun dato geografico. Vai su 'Gestione Dati' per scaricarlo.")
        with c_sec:
            if total_sec:
                df_s = pd.DataFrame(list(total_sec.items()), columns=['Settore', 'Valore'])
                fig2 = px.pie(df_s, values='Valore', names='Settore', hole=0.4, title="Esposizione Settoriale Totale")
                fig2 = style_chart_for_mobile(fig2)
                fig2.update_traces(textinfo='percent', hovertemplate='<b>%{label}</b><br>€%{value:,.0f}<br>%{percent}<extra></extra>')
                fig2.update_layout(showlegend=False)
                st.plotly_chart(fig2, use_container_width=True)
            else: st.info("Nessun dato settoriale. Vai su 'Gestione Dati' per scaricarlo.")
    else: st.warning("Il valore del portafoglio è zero o i prezzi non sono aggiornati.")

st.divider()
st.subheader("📉 Andamento Temporale")
if not df_prices.empty and not df_full.empty:
    start_dt, end_dt = df_trans['date'].min(), datetime.today()
    full_idx = pd.date_range(start_dt, end_dt, freq='D').normalize()
    daily_qty_change = df_full.pivot_table(index='date', columns='ticker', values='quantity', aggfunc='sum').fillna(0)
    daily_holdings = daily_qty_change.reindex(full_idx, fill_value=0).cumsum()
    price_matrix = df_prices.pivot(index='date', columns='ticker', values='close_price').reindex(full_idx).ffill() 
    common_cols = daily_holdings.columns.intersection(price_matrix.columns)
    daily_value = (daily_holdings[common_cols] * price_matrix[common_cols]).sum(axis=1)
    daily_inv_change = df_full.pivot_table(index='date', values='local_value', aggfunc='sum').fillna(0)
    daily_invested = -daily_inv_change.reindex(full_idx, fill_value=0).cumsum()
    hdf = pd.DataFrame({'Data': full_idx, 'Valore': daily_value, 'Investito': daily_invested['local_value']})
    fig_hist = go.Figure()
    fig_hist.add_trace(go.Scatter(x=hdf['Data'], y=hdf['Valore'], fill='tozeroy', name='Valore Attuale', line_color='#00CC96'))
    fig_hist.add_trace(go.Scatter(x=hdf['Data'], y=hdf['Investito'], name='Soldi Versati', line=dict(color='#EF553B', dash='dash')))
    fig_hist = style_chart_for_mobile(fig_hist)
    st.plotly_chart(fig_hist, use_container_width=True)
else:
    st.info("Dati insufficienti per il grafico storico.")

st.subheader("📋 Dettaglio Asset (Clicca per Analisi)")
# La riga 'CASH' viene mostrata nella tabella
display_df = view[['product', 'ticker', 'quantity', 'net_invested', 'mkt_val', 'pnl%']].sort_values('mkt_val', ascending=False)
selection = st.dataframe(
    display_df.style.format({'quantity': "{:.2f}", 'net_invested': "€ {:.2f}", 'mkt_val': "€ {:.2f}", 'pnl%': "{:.2f}%"}).applymap(color_pnl, subset=['pnl%']),
    use_container_width=True, selection_mode="single-row", on_select="rerun", hide_index=True)

if selection.selection.rows:
    idx = selection.selection.rows[0]
    sel_ticker = display_df.iloc[idx]['ticker']
    # Impedisce il reindirizzamento se si clicca sulla riga della liquidità
    if sel_ticker != 'CASH':
        st.session_state['selected_ticker'] = sel_ticker
        st.switch_page("pages/1_Analisi_Asset.py")