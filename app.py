import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
from utils import get_data, save_data, color_pnl, make_sidebar, style_chart_for_mobile

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Portfolio Pro", layout="wide", page_icon="🚀")
make_sidebar()
st.title("🚀 Dashboard Portafoglio")

# Definiamo le categorie standard in un unico posto
CATEGORIE_ASSET = ["Azionario", "Obbligazionario", "Gold", "Liquidità"]

# --- CARICAMENTO DATI ---
with st.spinner("Caricamento dati..."):
    df_trans = get_data("transactions")
    df_map = get_data("mapping")
    df_prices = get_data("prices")
    df_settings = get_data("settings")
    df_budget = get_data("budget")

if df_trans.empty:
    st.info("👋 Benvenuto! Il database è vuoto. Vai su 'Gestione Dati' per importare il CSV."), st.stop()

# --- CONTROLLO MAPPATURA MANCANTE ---
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

# --- PREPARAZIONE DATI ---
df_trans['date'] = pd.to_datetime(df_trans['date'], errors='coerce').dt.normalize()
df_prices['date'] = pd.to_datetime(df_prices['date'], errors='coerce').dt.normalize()
if not df_budget.empty:
    df_budget['date'] = pd.to_datetime(df_budget['date'], errors='coerce').dt.normalize()

df_full = df_trans.merge(df_map, on='isin', how='left')
last_p = df_prices.sort_values('date').groupby('ticker').tail(1).set_index('ticker')['close_price']
view = df_full.groupby(['product', 'ticker', 'category']).agg({'quantity':'sum', 'local_value':'sum'}).reset_index()
view = view[view['quantity'] > 0.001] 
view['net_invested'] = -view['local_value']
view['curr_price'] = view['ticker'].map(last_p)
view['mkt_val'] = view['quantity'] * view['curr_price']
view['pnl'] = view['mkt_val'] - view['net_invested']
view['pnl%'] = (view['pnl'] / view['net_invested']) * 100

# --- LOGICA LIQUIDITA' A DUE MODALITA' (MANUALE/AUTOMATICA) ---
final_liquidity = 0.0
liquidity_label = "Liquidità"
manual_override = False

# 1. Controlla se esiste un override manuale
if not df_settings.empty:
    liquidity_setting = df_settings[df_settings['key'] == 'manual_liquidity']
    if not liquidity_setting.empty:
        manual_liquidity_value = float(liquidity_setting['value'].iloc[0])
        if manual_liquidity_value > 0:
            final_liquidity = manual_liquidity_value
            liquidity_label = "Liquidità Manuale"
            manual_override = True

# 2. Se non c'è override, calcola la liquidità automaticamente a partire dal primo movimento di budget
if not manual_override and not df_budget.empty and not df_trans.empty:
    # Trova la data del primo movimento di budget per iniziare il calcolo da lì
    start_date_budget = df_budget['date'].min()
    
    # Filtra i dati a partire da questa data
    budget_since_start = df_budget[df_budget['date'] >= start_date_budget]
    trans_since_start = df_trans[df_trans['date'] >= start_date_budget]
    
    # Calcola i totali sui dati filtrati
    total_entrate = budget_since_start[budget_since_start['type'] == 'Entrata']['amount'].sum()
    total_uscite = budget_since_start[budget_since_start['type'] == 'Uscita']['amount'].sum()
    total_investito_netto = -trans_since_start['local_value'].sum()
    
    # Liquidità = (Entrate da start) - (Uscite da start) - (Investito da start)
    final_liquidity = total_entrate - total_uscite - total_investito_netto
    liquidity_label = "Liquidità Calcolata"

# Aggiungi la liquidità finale (cash) al DataFrame 'view' per i grafici
if final_liquidity > 0:
    liquidita_row = pd.DataFrame([{'product': liquidity_label, 'ticker': 'CASH', 'category': 'Liquidità', 'quantity': 1, 'local_value': 0, 'net_invested': final_liquidity, 'curr_price': final_liquidity, 'mkt_val': final_liquidity, 'pnl': 0, 'pnl%': 0}])
    view = pd.concat([view, liquidita_row], ignore_index=True)

# --- KPI TOTALI ---
tot_val = view['mkt_val'].sum()
tot_inv = view['net_invested'].sum()
tot_pnl = tot_val - tot_inv
c1, c2, c3 = st.columns(3)
c1.metric("💰 Valore Totale", f"€ {tot_val:,.2f}")
c2.metric("💳 Capitale Investito", f"€ {tot_inv:,.2f}")
c3.metric("📈 P&L Netto", f"€ {tot_pnl:,.2f}", delta=f"{(tot_pnl/tot_inv)*100:.2f}%" if tot_inv else "0%")
st.divider()

# --- SEZIONE COMPOSIZIONE PORTAFOGLIO CON TABS ---
st.subheader("🔬 Analisi Composizione Portafoglio")
tab1, tab2, tab3, tab4, tab5 = st.tabs(["Asset Class", "Azioni/Obbligazioni/Gold", "Tutti gli Asset", "Dettaglio Azionario", "Dettaglio Obbligazionario"])

with tab1:
    composition_data = view.groupby('category')['mkt_val'].sum().reset_index()
    color_map = {'Azionario': '#636EFA', 'Obbligazionario': '#00CC96', 'Gold': '#FFA15A', 'Liquidità': '#AB63FA', 'Altro': '#B6E880'}
    fig_cat = px.pie(composition_data, values='mkt_val', names='category', title='Suddivisione per Asset Class', color='category', color_discrete_map=color_map)
    fig_cat = style_chart_for_mobile(fig_cat)
    fig_cat.update_traces(textinfo='percent+value', texttemplate='%{percent} <br>€%{value:,.0f}', hovertemplate='<b>%{label}</b><br>Valore: €%{value:,.2f}<br>(%{percent})<extra></extra>')
    fig_cat.update_layout(showlegend=True)
    st.plotly_chart(fig_cat, use_container_width=True)

with tab2:
    # Filtra i dati per includere solo le categorie desiderate
    categories_to_show = ['Azionario', 'Obbligazionario', 'Gold']
    filtered_data = view[view['category'].isin(categories_to_show)]
    
    # Raggruppa i dati filtrati
    composition_data = filtered_data.groupby('category')['mkt_val'].sum().reset_index()
    
    color_map = {
        'Azionario': '#636EFA',
        'Obbligazionario': '#00CC96',
        'Gold': '#FFA15A'
    }
    
    fig_simple = px.pie(composition_data, values='mkt_val', names='category', title='Ripartizione: Azioni / Obbligazioni / Gold', color='category', color_discrete_map=color_map)
    fig_simple = style_chart_for_mobile(fig_simple)
    fig_simple.update_traces(textinfo='percent+value', texttemplate='%{percent} <br>€%{value:,.0f}', hovertemplate='<b>%{label}</b><br>Valore: €%{value:,.2f}<br>(%{percent})<extra></extra>')
    fig_simple.update_layout(showlegend=True)
    st.plotly_chart(fig_simple, use_container_width=True)

with tab3:
    if not view.empty:
        fig_all_assets = px.pie(view, values='mkt_val', names='product', title='Composizione per singolo Asset')
        fig_all_assets = style_chart_for_mobile(fig_all_assets)
        fig_all_assets.update_traces(textinfo='percent', hovertemplate='<b>%{label}</b><br>Valore: €%{value:,.2f}<br>(%{percent})<extra></extra>')
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
    else:
        st.info("Nessun asset azionario in portafoglio.")

with tab5:
    df_obbligazionario = view[view['category'] == 'Obbligazionario']
    if not df_obbligazionario.empty:
        fig_bond = px.pie(df_obbligazionario, values='mkt_val', names='product', title='Composizione Portafoglio Obbligazionario')
        fig_bond = style_chart_for_mobile(fig_bond)
        fig_bond.update_traces(textinfo='percent', hovertemplate='<b>%{label}</b><br>Valore: €%{value:,.2f}<br>(%{percent})<extra></extra>')
        fig_bond.update_layout(showlegend=False)
        st.plotly_chart(fig_bond, use_container_width=True)
    else:
        st.info("Nessun asset obbligazionario in portafoglio.")

st.divider()

# --- GRAFICO STORICO ---
st.subheader("📉 Andamento Temporale")
if not df_prices.empty and not df_full.empty:
    start_dt = df_trans['date'].min()
    end_dt = datetime.today()
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

# --- TABELLA INTERATTIVA ---
st.subheader("📋 Dettaglio Asset (Clicca per Analisi)")
display_df = view[['product', 'ticker', 'quantity', 'net_invested', 'mkt_val', 'pnl%']].sort_values('mkt_val', ascending=False)
selection = st.dataframe(
    display_df.style.format({'quantity': "{:.2f}", 'net_invested': "€ {:.2f}", 'mkt_val': "€ {:.2f}", 'pnl%': "{:.2f}%"}).applymap(color_pnl, subset=['pnl%']),
    use_container_width=True, selection_mode="single-row", on_select="rerun", hide_index=True)
if selection.selection.rows:
    idx = selection.selection.rows[0]
    sel_ticker = display_df.iloc[idx]['ticker']
    st.session_state['selected_ticker'] = sel_ticker
    st.switch_page("pages/1_Analisi_Asset.py")