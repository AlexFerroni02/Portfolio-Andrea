import streamlit as st
import pandas as pd
import json
import numpy as np
from datetime import date
from database.connection import get_data, save_data, save_allocation_json
from services.data_service import (
    process_new_transactions, 
    calculate_net_worth_snapshot,
    sync_prices,
    fetch_justetf_allocation_robust
)

CATEGORIE_ASSET = ["Azionario", "Obbligazionario", "Gold", "Liquidità"]

def render_import_tab():
    st.write("Carica il file `Transactions.csv` di DEGIRO.")
    up = st.file_uploader("Upload CSV", type=['csv'], key="csv_uploader")
    if up and st.button("Importa Transazioni"):
        with st.spinner("Importazione in corso..."):
            df_trans = get_data("transactions")
            new_df = process_new_transactions(up, df_trans)
            if not new_df.empty:
                save_data(new_df, "transactions", method='append')
                st.success(f"✅ Importate {len(new_df)} nuove transazioni!")
                st.rerun()
            else:
                st.info("Nessuna nuova transazione trovata.")

def render_mapping_tab():
    st.subheader("Modifica, Aggiungi o Elimina Mappature")
    st.caption("Fai doppio clic su una cella per modificarla. Aggiungi una riga in fondo per una nuova mappatura.")

    df_map = get_data("mapping")
    df_trans = get_data("transactions")
    # Filtra solo gli ISIN posseduti (quantità > 0)
    if not df_trans.empty:
        holdings = df_trans.groupby('isin')['quantity'].sum()
        owned_isin = holdings[holdings > 0].index.tolist()
        df_map = df_map[df_map['isin'].isin(owned_isin)]

    # 1. Reset dell'indice (spesso è questo che appare come colonna extra)
    df_map = df_map.reset_index(drop=True)

    df_map_edit = df_map.copy()

    # 2. Rimuovi qualsiasi colonna che si chiami 'id' (maiuscolo o minuscolo)
    cols_to_drop = [c for c in df_map_edit.columns if c.lower() == 'id']
    if cols_to_drop:
        df_map_edit = df_map_edit.drop(columns=cols_to_drop)

    df_map_edit.insert(0, "Elimina", False)
    
    # 3. Aggiungi "id": None nella configurazione per nasconderla forzatamente
    edited_df = st.data_editor(df_map_edit, num_rows="dynamic", use_container_width=True, hide_index=True,
        column_config={
            "Elimina": st.column_config.CheckboxColumn(required=True),
            "isin": st.column_config.TextColumn("ISIN (Obbligatorio)", required=True),
            "ticker": st.column_config.TextColumn("Ticker Yahoo (Obbligatorio)", required=True),
            "category": st.column_config.SelectboxColumn("Categoria (Obbligatorio)", options=CATEGORIE_ASSET, required=True,),
            "proxy_ticker": None,
            "id": None  # <--- Nascondi forzatamente se dovesse ancora esserci
        })
    if st.button("💾 Salva Modifiche Mappatura", type="primary"):
        df_to_process = edited_df.copy()
        df_to_process = df_to_process[df_to_process["Elimina"] == False].drop(columns=["Elimina"])
        df_to_process.dropna(subset=['isin'], inplace=True)
        df_to_process = df_to_process[df_to_process['isin'].str.strip() != '']
        df_to_process.drop_duplicates(subset=['isin'], keep='last', inplace=True)
        save_data(df_to_process, "mapping", method='replace')
        st.success("✅ Mappatura aggiornata con successo!")
        st.rerun()

def render_prices_tab():
    st.write("Scarica gli ultimi prezzi di chiusura da Yahoo Finance **solo per gli asset che possiedi**.")
    if st.button("Avvia Sincronizzazione Prezzi"):
        df_trans, df_map = get_data("transactions"), get_data("mapping")
        if not df_map.empty and not df_trans.empty:
            n = sync_prices(df_trans, df_map)
            if n > 0: st.success(f"✅ Aggiornamento completato: {n} nuovi prezzi salvati.")
            else: st.info("Tutti i prezzi per gli asset posseduti sono già aggiornati.")
        else:
            st.error("Database transazioni o mappatura vuoto. Impossibile aggiornare i prezzi.")

def render_budget_tab(initial_balance_exists: bool):
    st.header("➕ Inserimento Rapido Movimenti")
    CATEGORIE_ENTRATE_BASE = ["Stipendio", "Bonus", "Regali", "Dividendi", "Rimborso", "Altro", "Aggiustamento Liquidità"]
    CATEGORIE_USCITE = ["Affitto/Casa", "Spesa Alimentare", "Ristoranti/Svago", "Trasporti", "Viaggi", "Salute", "Shopping", "Bollette", "Altro", "Aggiustamento Liquidità"]
    if not initial_balance_exists:
        CATEGORIE_ENTRATE = ["Saldo Iniziale"] + CATEGORIE_ENTRATE_BASE
        st.warning("**Imposta il tuo Saldo Iniziale!**\n\nQuesto è il primo passo fondamentale.", icon="🎯")
    else:
        CATEGORIE_ENTRATE = CATEGORIE_ENTRATE_BASE
        st.success("✅ Hai già inserito un 'Saldo Iniziale'.", icon="👍")
    st.info("💡 Usa 'Aggiustamento Liquidità' per correggere eventuali discrepanze future.")
    col_date, col_type = st.columns(2)
    selected_date = col_date.date_input("Data per i movimenti", date.today(), key="batch_date")
    f_type = col_type.radio("Tipo Movimento:", ["Uscita", "Entrata"], horizontal=True, key="budget_type_radio")
    with st.form("batch_form", clear_on_submit=True):
        active_categories = CATEGORIE_USCITE if f_type == "Uscita" else CATEGORIE_ENTRATE
        st.subheader(f"🔴 Inserisci Uscite" if f_type == "Uscita" else "🟢 Inserisci Entrate")
        for cat in active_categories:
            st.markdown(f"**{cat}**")
            col_val, col_note = st.columns(2)
            col_val.number_input("Importo", label_visibility="collapsed", key=f"movimento_{cat}", min_value=0.0, value=0.0, format="%.2f")
            col_note.text_input("Note", label_visibility="collapsed", key=f"nota_{cat}", placeholder="Nota opzionale...")
            st.divider()
        if st.form_submit_button("💾 Salva Movimenti", type="primary", use_container_width=True):
            rows_to_add = [{'date': pd.to_datetime(selected_date), 'type': f_type, 'category': cat, 'amount': st.session_state[f"movimento_{cat}"], 'note': st.session_state[f"nota_{cat}"] or ''} for cat in active_categories if st.session_state[f"movimento_{cat}"] > 0]
            if rows_to_add:
                save_data(pd.DataFrame(rows_to_add), "budget", method='append')
                st.success(f"✅ Salvati {len(rows_to_add)} nuovi movimenti!")
                st.rerun()
    st.divider()
    st.subheader("Storico Movimenti (Modifica o Elimina)")
    df_budget_all = get_data("budget")
    if not df_budget_all.empty:
        df_budget_all['date'] = pd.to_datetime(df_budget_all['date']).dt.date
        df_edit = df_budget_all.sort_values('date', ascending=False).copy()
        df_edit.insert(0, "Elimina", False)
        all_categories = sorted(list(set(CATEGORIE_ENTRATE_BASE + CATEGORIE_USCITE + ["Saldo Iniziale"])))
        edited_budget = st.data_editor(df_edit, use_container_width=True, hide_index=True, num_rows="dynamic", key="budget_editor",
            column_config={
                "Elimina": st.column_config.CheckboxColumn(required=True),
                "date": st.column_config.DateColumn("Data", format="DD/MM/YYYY", required=True),
                "type": st.column_config.SelectboxColumn("Tipo", options=["Entrata", "Uscita"], required=True),
                "category": st.column_config.SelectboxColumn("Categoria", options=all_categories, required=True),
                "amount": st.column_config.NumberColumn("Importo", format="€ %.2f", required=True),
                "note": st.column_config.TextColumn("Note")
            })
        if st.button("💾 Salva Modifiche Movimenti", type="primary"):
            df_to_save = pd.DataFrame(edited_budget)
            df_to_save = df_to_save[df_to_save["Elimina"] == False].drop(columns=["Elimina"])
            save_data(df_to_save, "budget", method='replace')
            st.success("✅ Movimenti aggiornati!")
            st.rerun()

def render_allocation_tab():
    st.subheader("Scarica e Modifica Dati di Allocazione (X-Ray)")
    df_map, df_trans, df_alloc = get_data("mapping"), get_data("transactions"), get_data("asset_allocation")
    if df_map.empty or df_trans.empty:
        st.warning("Mancano transazioni o mappatura.")
        return
    df_full = df_trans.merge(df_map, on='isin', how='left')
    holdings = df_full.groupby(['product', 'ticker', 'isin']).agg(quantity=('quantity', 'sum')).reset_index()
    view = holdings[holdings['quantity'] > 0.001].copy()
    options = view.apply(lambda x: f"{x['product']} ({x['ticker']})", axis=1).unique()
    st.subheader("1. Scarica Nuovi Dati")
    col_sel, col_btn = st.columns([3, 1])
    selected_option = col_sel.selectbox("Seleziona un asset da analizzare:", options, key="asset_selector_alloc")
    if col_btn.button("⚡ Analizza Asset (JustETF)", type="primary"):
        with st.spinner("Scraping in corso..."):
            sel_ticker = selected_option.split('(')[-1].replace(')', '')
            sel_isin = view[view['ticker'] == sel_ticker].iloc[0]['isin']
            geo, sec = fetch_justetf_allocation_robust(sel_isin)
            st.session_state.scraped_data = {'ticker': sel_ticker, 'geo': geo, 'sec': sec} if geo or sec else None
            if st.session_state.scraped_data: st.success(f"Dati per {sel_ticker} scaricati! Vai al punto 2.")
            else: st.error("Nessun dato di allocazione trovato per questo ISIN.")
    if st.session_state.get('scraped_data'):
        st.subheader("2. Verifica e Salva Dati")
        data = st.session_state.scraped_data
        with st.form("verify_and_save_form"):
            c1, c2 = st.columns(2)
            geo_text = c1.text_area("JSON Geografico", value=json.dumps(data['geo'], indent=2, ensure_ascii=False), height=300)
            sec_text = c2.text_area("JSON Settoriale", value=json.dumps(data['sec'], indent=2, ensure_ascii=False), height=300)
            if st.form_submit_button("💾 Salva Dati nel Database", type="primary"):
                try:
                    save_allocation_json(data['ticker'], json.loads(geo_text), json.loads(sec_text))
                    st.success(f"Dati per {data['ticker']} salvati!")
                    st.session_state.scraped_data = None
                    st.rerun()
                except json.JSONDecodeError: st.error("Formato JSON non valido.")
    st.divider()
    st.subheader("3. Modifica Dati Esistenti")
    if not df_alloc.empty:
        ticker_to_edit = st.selectbox("Seleziona un asset da modificare:", df_alloc['ticker'].unique(), key="alloc_ticker_edit")
        if ticker_to_edit:
            record = df_alloc[df_alloc['ticker'] == ticker_to_edit].iloc[0]
            with st.form(f"edit_alloc_form_{ticker_to_edit}"):
                c1, c2 = st.columns(2)
                try:
                    geo_raw = record.get('geography_json')
                    sec_raw = record.get('sector_json')
                    geo_db = geo_raw if isinstance(geo_raw, dict) else json.loads(geo_raw or '{}')
                    sec_db = sec_raw if isinstance(sec_raw, dict) else json.loads(sec_raw or '{}')
                except (json.JSONDecodeError, TypeError):
                    geo_db, sec_db = {}, {}
                geo_text_edit = c1.text_area("JSON Geo", value=json.dumps(geo_db, indent=2, ensure_ascii=False), height=300, key=f"geo_{ticker_to_edit}")
                sec_text_edit = c2.text_area("JSON Sec", value=json.dumps(sec_db, indent=2, ensure_ascii=False), height=300, key=f"sec_{ticker_to_edit}")
                if st.form_submit_button("💾 Aggiorna Dati"):
                    try:
                        save_allocation_json(ticker_to_edit, json.loads(geo_text_edit), json.loads(sec_text_edit))
                        st.success(f"Dati per {ticker_to_edit} aggiornati!")
                        st.rerun()
                    except json.JSONDecodeError: st.error("Formato JSON non valido.")
    else:
        st.info("Nessun dato di allocazione ancora salvato.")

def render_net_worth_tab():
    st.subheader("🎯 Gestione Patrimonio Netto")
    
    # --- 1. SNAPSHOT AUTOMATICO ---
    st.markdown("### 1. Snapshot Automatico")
    snapshot_date_input = st.date_input("Data per lo Snapshot", date.today(), key="snapshot_date_input")
    
    if st.button("Calcola Patrimonio a questa data"):
        with st.spinner("Calcolo in corso..."):
            snapshot_date = pd.to_datetime(snapshot_date_input).normalize()
            dfs = {name: get_data(name) for name in ["transactions", "mapping", "prices", "budget"]}
            st.session_state.calculated_snapshot = {"date": snapshot_date, "values": calculate_net_worth_snapshot(snapshot_date, **dfs)}
            
    if st.session_state.get('calculated_snapshot'):
        snap = st.session_state.calculated_snapshot
        net_worth, assets_val, liquidity_val = snap['values']
        st.metric(f"Patrimonio Calcolato al {snap['date'].strftime('%d-%m-%Y')}", f"€ {net_worth:,.2f}", f"Asset: € {assets_val:,.2f} | Liquidità: € {liquidity_val:,.2f}")
        
        if st.button("💾 Salva questo Snapshot", type="primary"):
            df_history = get_data("networth_history")
            new_snapshot = pd.DataFrame([{'date': snap['date'], 'net_worth': net_worth}])
            df_merged = pd.concat([df_history, new_snapshot]).drop_duplicates(subset='date', keep='last')
            save_data(df_merged.sort_values('date'), "networth_history", method='replace')
            st.success("Snapshot salvato!"); st.session_state.calculated_snapshot = None; st.rerun()
            
    st.divider()

    # --- 2. AGGIUNTA MANUALE ---
    st.markdown("### 2. Aggiunta Manuale Rapida")
    with st.form("manual_add_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        manual_date = c1.date_input("Data", key="manual_date_input")
        manual_nw = c2.number_input("Patrimonio Netto (€)", min_value=0.0, format="%.2f")
        
        if st.form_submit_button("➕ Aggiungi Valore Manuale") and manual_nw > 0:
            df_history = get_data("networth_history")
            new_entry = pd.DataFrame([{'date': pd.to_datetime(manual_date), 'net_worth': manual_nw}])
            df_merged = pd.concat([df_history, new_entry]).drop_duplicates(subset='date', keep='last')
            save_data(df_merged.sort_values('date'), "networth_history", method='replace')
            st.success("Valore aggiunto!"); st.rerun()
            
    st.divider()

    # --- 3. MODIFICA STORICO ---
    st.markdown("### 3. Modifica o Elimina Storico")
    df_history_full = get_data("networth_history")
    
    df_nw_edit = pd.DataFrame(columns=['date', 'net_worth'])
    if not df_history_full.empty and 'net_worth' in df_history_full.columns:
        df_nw_edit = df_history_full[['date', 'net_worth']].dropna(subset=['net_worth']).copy()
        if not df_nw_edit.empty:
            df_nw_edit['date'] = pd.to_datetime(df_nw_edit['date']).dt.date

    df_nw_edit = df_nw_edit.reset_index(drop=True)
    cols_to_drop = [c for c in df_nw_edit.columns if c.lower() == 'id']
    if cols_to_drop: df_nw_edit = df_nw_edit.drop(columns=cols_to_drop)
    
    df_nw_edit.insert(0, "Elimina", False)

    edited_nw = st.data_editor(
        df_nw_edit.sort_values('date', ascending=False), 
        num_rows="dynamic", 
        use_container_width=True, 
        hide_index=True, 
        key="nw_editor",
        column_config={
            "Elimina": st.column_config.CheckboxColumn(required=True),
            "date": st.column_config.DateColumn("Data", required=True), 
            "net_worth": st.column_config.NumberColumn("Patrimonio Netto (€)", format="€ %.2f", required=True),
            "id": None
        }
    )

    if st.button("💾 Salva Modifiche Storico", type="primary"):
        df_new_nw = pd.DataFrame(edited_nw)
        df_new_nw = df_new_nw[df_new_nw["Elimina"] == False].drop(columns=["Elimina"])
        if "id" in df_new_nw.columns: df_new_nw = df_new_nw.drop(columns=["id"])

        df_goals_only = pd.DataFrame(columns=['date', 'goal'])
        if not df_history_full.empty and 'goal' in df_history_full.columns:
            df_goals_only = df_history_full[['date', 'goal']].dropna(subset=['goal'])

        if not df_new_nw.empty:
            df_new_nw['date'] = pd.to_datetime(df_new_nw['date'])
            df_final = pd.merge(df_new_nw, df_goals_only, on='date', how='outer')
        else:
            df_final = df_goals_only

        save_data(df_final.sort_values('date'), "networth_history", method='replace')
        st.success("Storico aggiornato!"); st.rerun()
            
    st.divider()

    # --- 4. OBIETTIVI FUTURI ---
    st.markdown("### 4. Imposta Obiettivi Futuri")
    
    # Preparazione dati puliti
    df_goals_edit = pd.DataFrame(columns=['date', 'goal'])
    if not df_history_full.empty and 'goal' in df_history_full.columns:
        df_goals_edit = df_history_full[['date', 'goal']].dropna(subset=['goal']).copy()
        if not df_goals_edit.empty:
            df_goals_edit['date'] = pd.to_datetime(df_goals_edit['date']).dt.date

    # Pulizia robusta ID e Indice
    df_goals_edit = df_goals_edit.reset_index(drop=True)
    cols_to_drop_g = [c for c in df_goals_edit.columns if c.lower() == 'id']
    if cols_to_drop_g: df_goals_edit = df_goals_edit.drop(columns=cols_to_drop_g)

    df_goals_edit.insert(0, "Elimina", False)

    edited_goals = st.data_editor(
        df_goals_edit.sort_values('date'), 
        num_rows="dynamic", 
        use_container_width=True, 
        hide_index=True, 
        key="goal_editor",
        column_config={
            "Elimina": st.column_config.CheckboxColumn(required=True),
            "date": st.column_config.DateColumn("Data Obiettivo", required=True), 
            "goal": st.column_config.NumberColumn("Obiettivo (€)", format="€ %.2f", required=True),
            "id": None
        }
    )

    if st.button("💾 Salva Obiettivi"):
        # Filtra eliminati e pulisci
        df_new_goals = pd.DataFrame(edited_goals)
        df_new_goals = df_new_goals[df_new_goals["Elimina"] == False].drop(columns=["Elimina"])
        if "id" in df_new_goals.columns: df_new_goals = df_new_goals.drop(columns=["id"])

        # Ricarica per sicurezza lo stato attuale
        df_history_curr = get_data("networth_history")
        
        if not df_new_goals.empty: 
            df_new_goals['date'] = pd.to_datetime(df_new_goals['date']).dt.normalize()
        
        # Logica di merge complessa per mantenere i dati esistenti
        df_combined = pd.concat([df_history_curr, df_new_goals]).drop_duplicates(subset=['date'], keep='last').sort_values('date')
        
        # Ricostruzione pulita
        df_nw_points = df_combined[['date', 'net_worth']].dropna()
        df_goal_points = df_combined[['date', 'goal']].dropna()
        
        if not df_goal_points.empty:
            df_final = pd.merge_asof(df_nw_points.sort_values('date'), df_goal_points.sort_values('date'), on='date', direction='forward')
            # Aggiungi anche i goal futuri che non hanno ancora un net_worth corrispondente
            df_final = pd.concat([df_final, df_goal_points]).drop_duplicates(subset=['date'], keep='last').sort_values('date')
        else:
            df_final = df_nw_points
            df_final['goal'] = np.nan
            
        # Pulizia finale: rimuovi righe vuote o goal passati inutili
        future_goals = df_final['date'] > pd.Timestamp.now().normalize()
        df_final = df_final[df_final['net_worth'].notna() | (df_final['goal'].notna() & future_goals)]
        save_data(df_final, "networth_history", method='replace')
        st.success("Obiettivi salvati e propagati!"); st.rerun()