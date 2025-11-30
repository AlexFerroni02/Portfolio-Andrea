import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from utils import get_data, save_data, make_sidebar, style_chart_for_mobile

st.set_page_config(page_title="Bilancio", layout="wide", page_icon="💰")
make_sidebar()
st.title("💰 Bilancio & Risparmio")

# --- CARICAMENTO DATI ---
df_budget = get_data("budget")
df_trans = get_data("transactions")
df_settings = get_data("settings")

if not df_budget.empty:
    df_budget['date'] = pd.to_datetime(df_budget['date'], errors='coerce').dt.normalize()
if not df_trans.empty:
    df_trans['date'] = pd.to_datetime(df_trans['date'], errors='coerce').dt.normalize()

if df_budget.empty:
    st.info("👋 Nessun dato presente. Vai su **Gestione Dati** per inserire entrate e uscite.")
    st.stop()

df_budget['mese_anno'] = df_budget['date'].dt.strftime('%Y-%m')
mesi_disponibili = sorted(df_budget['mese_anno'].unique(), reverse=True)

col_sel, col_msg = st.columns([1, 3])
selected_month = col_sel.selectbox("Seleziona Mese:", mesi_disponibili)
col_msg.caption("💡 Per aggiungere nuovi movimenti, vai alla pagina **Gestione Dati**.")

df_month = df_budget[df_budget['mese_anno'] == selected_month]

entrate = df_month[df_month['type'] == 'Entrata']['amount'].sum()
uscite = df_month[df_month['type'] == 'Uscita']['amount'].sum()
risparmio = entrate - uscite
savings_rate = (risparmio / entrate * 100) if entrate > 0 else 0

investito_mese = 0.0
if not df_trans.empty:
    mask_inv = df_trans['date'].dt.strftime('%Y-%m') == selected_month
    investito_mese = -df_trans[mask_inv]['local_value'].sum()

# --- LOGICA LIQUIDITA' A DUE MODALITA' (per KPI) ---
final_liquidity = 0.0
liquidity_help_text = "Nessun dato per il calcolo."
manual_override = False

# 1. Controlla se esiste un override manuale
if not df_settings.empty:
    liquidity_setting = df_settings[df_settings['key'] == 'manual_liquidity']
    if not liquidity_setting.empty:
        manual_liquidity_value = float(liquidity_setting['value'].iloc[0])
        if manual_liquidity_value > 0:
            final_liquidity = manual_liquidity_value
            liquidity_help_text = "Modalità Manuale: valore impostato in 'Gestione Dati'."
            manual_override = True

# 2. Se non c'è override, calcola la liquidità automaticamente a partire dal primo movimento di budget
if not manual_override and not df_budget.empty and not df_trans.empty:
    start_date_budget = df_budget['date'].min()
    
    budget_since_start = df_budget[df_budget['date'] >= start_date_budget]
    trans_since_start = df_trans[df_trans['date'] >= start_date_budget]
    
    total_entrate = budget_since_start[budget_since_start['type'] == 'Entrata']['amount'].sum()
    total_uscite = budget_since_start[budget_since_start['type'] == 'Uscita']['amount'].sum()
    total_investito_netto = -trans_since_start['local_value'].sum()
    
    final_liquidity = total_entrate - total_uscite - total_investito_netto
    liquidity_help_text = f"Modo Automatico: calcolo dal {start_date_budget.strftime('%d-%m-%Y')}"

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Entrate Mese", f"€ {entrate:,.2f}")
k2.metric("Uscite Mese", f"€ {uscite:,.2f}", delta=f"-{(uscite/entrate)*100:.1f}%" if entrate else "")
k3.metric("Risparmio Mese", f"€ {risparmio:,.2f}", delta=f"{savings_rate:.1f}% SR")
k4.metric("Investito Mese", f"€ {investito_mese:,.2f}", delta=f"{(investito_mese/risparmio)*100:.1f}% del risparmio" if risparmio > 0 else "0%")
k5.metric("Liquidità Totale", f"€ {final_liquidity:,.2f}", help=liquidity_help_text)

st.divider()

c1, c2 = st.columns(2)
with c1:
    st.subheader("💸 Spese per Categoria")
    df_spese = df_month[df_month['type'] == 'Uscita']
    if not df_spese.empty:
        fig_pie = px.pie(df_spese, values='amount', names='category', hole=0.4)
        fig_pie = style_chart_for_mobile(fig_pie)
        fig_pie.update_layout(showlegend=False)
        st.plotly_chart(fig_pie, use_container_width=True)
    else:
        st.info("Nessuna spesa registrata in questo mese.")

with c2:
    st.subheader("🌊 Flusso Mensile")
    fig_bar = go.Figure()
    fig_bar.add_trace(go.Bar(name='Entrate', x=['Flusso'], y=[entrate], marker_color='#28a745'))
    fig_bar.add_trace(go.Bar(name='Spese', x=['Flusso'], y=[uscite], marker_color='#dc3545'))
    fig_bar.add_trace(go.Bar(name='Investito', x=['Flusso'], y=[investito_mese], marker_color='#007bff'))
    fig_bar.update_layout(barmode='group')
    fig_bar = style_chart_for_mobile(fig_bar)
    st.plotly_chart(fig_bar, use_container_width=True)

st.subheader("📝 Dettaglio Movimenti")
with st.expander("Visualizza o Elimina Movimenti"):
    df_edit = df_month.copy()
    df_edit.insert(0, "Elimina", False)
    edited_df = st.data_editor(
        df_edit,
        column_config={"Elimina": st.column_config.CheckboxColumn(default=False), "date": st.column_config.DateColumn("Data", format="DD-MM-YYYY"), "amount": st.column_config.NumberColumn("Importo", format="€ %.2f")},
        disabled=["date", "type", "category", "amount", "note"],
        hide_index=True, use_container_width=True
    )
    to_delete = edited_df[edited_df["Elimina"] == True]
    if not to_delete.empty:
        if st.button("🗑️ CONFERMA ELIMINAZIONE", type="primary"):
            indexes_to_drop = to_delete.index
            df_budget_updated = df_budget.drop(indexes_to_drop)
            save_data(df_budget_updated, "budget", method='replace') 
            st.success("✅ Eliminato! La pagina si aggiornerà.") 
            st.rerun()