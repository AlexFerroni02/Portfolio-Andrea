import streamlit as st
import pandas as pd
from datetime import date
import json
from utils import get_data, save_data, parse_degiro_csv, generate_id, sync_prices, make_sidebar, fetch_justetf_allocation_robust, save_allocation_json

st.set_page_config(page_title="Gestione Dati", page_icon="📂", layout="wide")
make_sidebar()
st.title("📂 Gestione Database")

CATEGORIE_ASSET = ["Azionario", "Obbligazionario", "Gold", "Liquidità"]

# Inizializza session_state per la verifica dei dati di allocazione
if 'scraped_data' not in st.session_state:
    st.session_state.scraped_data = None

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📥 Importa CSV", "🔗 Mappatura Ticker", "🔄 Aggiorna Prezzi", "💸 Movimenti Bilancio", "💰 Liquidità", "🔬 Allocazione Asset (X-Ray)"])

# --- TAB 1: IMPORT ---
with tab1:
    st.write("Carica il file `Transactions.csv` di DEGIRO.")
    up = st.file_uploader("Upload CSV", type=['csv'])
    if up and st.button("Importa Transazioni"):
        with st.spinner("Importazione in corso..."):
            ndf = parse_degiro_csv(up)
            df_trans = get_data("transactions")
            rows_to_add = []
            existing_ids = set(df_trans['id']) if not df_trans.empty else set()
            for idx, r in ndf.iterrows():
                if pd.isna(r.get('ISIN')): continue
                tid = generate_id(r, idx)
                if tid not in existing_ids:
                    val = r.get('Totale', 0) if r.get('Totale', 0) != 0 else r.get('Valore', 0)
                    rows_to_add.append({'id': tid, 'date': r['Data'], 'product': r.get('Prodotto',''), 'isin': r.get('ISIN',''), 'quantity': r.get('Quantità',0), 'local_value': val, 'fees': r.get('Costi di transazione',0), 'currency': 'EUR'})
                    existing_ids.add(tid)
            if rows_to_add:
                new_df = pd.DataFrame(rows_to_add)
                save_data(new_df, "transactions", method='append')
                st.success(f"✅ Importate {len(rows_to_add)} nuove transazioni!")
            else:
                st.info("Nessuna nuova transazione trovata.")

# --- TAB 2: MAPPATURA INTERATTIVA ---
with tab2:
    st.subheader("Modifica, Aggiungi o Elimina Mappature")
    st.caption("Fai doppio clic su una cella per modificarla. Aggiungi una riga in fondo per una nuova mappatura.")
    df_map = get_data("mapping")
    df_map_edit = df_map.copy()
    df_map_edit.insert(0, "Elimina", False)
    edited_df = st.data_editor(df_map_edit, num_rows="dynamic", use_container_width=True, hide_index=True,
        column_config={
            "Elimina": st.column_config.CheckboxColumn(required=True),
            "isin": st.column_config.TextColumn("ISIN (Obbligatorio)", required=True),
            "ticker": st.column_config.TextColumn("Ticker Yahoo (Obbligatorio)", required=True),
            "category": st.column_config.SelectboxColumn("Categoria (Obbligatorio)", options=CATEGORIE_ASSET, required=True,)
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

# --- TAB 3: PREZZI ---
with tab3:
    st.write("Scarica gli ultimi prezzi di chiusura da Yahoo Finance **solo per gli asset che possiedi**.")
    if st.button("Avvia Sincronizzazione Prezzi"):
        df_trans, df_map = get_data("transactions"), get_data("mapping")
        if not df_map.empty and not df_trans.empty:
            n = sync_prices(df_trans, df_map)
            if n > 0: st.success(f"✅ Aggiornamento completato: {n} nuovi prezzi salvati.")
            else: st.info("Tutti i prezzi per gli asset posseduti sono già aggiornati.")
        else:
            st.error("Database transazioni o mappatura vuoto. Impossibile aggiornare i prezzi.")

# --- TAB 4: MOVIMENTI BILANCIO (LAYOUT VERTICALE) ---
with tab4:
    st.header("➕ Inserimento Rapido Movimenti")
    CATEGORIE_ENTRATE = ["Stipendio", "Bonus", "Regali", "Dividendi", "Rimborso", "Altro"]
    CATEGORIE_USCITE = ["Affitto/Casa", "Spesa Alimentare", "Ristoranti/Svago", "Trasporti", "Viaggi", "Salute", "Shopping", "Bollette", "Altro"]
    col_date, col_type = st.columns(2)
    selected_date = col_date.date_input("Data per i movimenti", date.today(), key="batch_date")
    f_type = col_type.radio("Tipo Movimento:", ["Uscita", "Entrata"], horizontal=True, key="budget_type_radio")
    st.divider()
    with st.form("batch_form", clear_on_submit=True):
        active_categories = CATEGORIE_USCITE if f_type == "Uscita" else CATEGORIE_ENTRATE
        if f_type == "Uscita": st.subheader("🔴 Inserisci Uscite")
        else: st.subheader("🟢 Inserisci Entrate")
        for cat in active_categories:
            st.markdown(f"**{cat}**")
            col_val, col_note = st.columns(2)
            col_val.number_input("Importo", label_visibility="collapsed", key=f"movimento_{cat}", min_value=0.0, value=0.0, format="%.2f")
            col_note.text_input("Note", label_visibility="collapsed", key=f"nota_{cat}", placeholder="Nota opzionale...")
            st.divider()
        submitted = st.form_submit_button("💾 Salva Movimenti", type="primary", use_container_width=True)
        if submitted:
            rows_to_add = []
            for cat in active_categories:
                amount = st.session_state[f"movimento_{cat}"]
                note = st.session_state[f"nota_{cat}"]
                if amount > 0:
                    rows_to_add.append({'date': pd.to_datetime(selected_date), 'type': f_type, 'category': cat, 'amount': amount, 'note': note if note else ''})
            if rows_to_add:
                new_entries_df = pd.DataFrame(rows_to_add)
                save_data(new_entries_df, "budget", method='append')
                st.success(f"✅ Salvati {len(rows_to_add)} nuovi movimenti!")
            else:
                st.warning("Nessun importo inserito. Nessun movimento salvato.")
    st.subheader("Ultimi Movimenti Inseriti")
    df_budget_display = get_data("budget")
    if not df_budget_display.empty:
        df_budget_display['date'] = pd.to_datetime(df_budget_display['date'])
        cols_to_show = ['date', 'type', 'category', 'amount', 'note']
        st.dataframe(df_budget_display[cols_to_show].sort_values('date', ascending=False).head(10), use_container_width=True, hide_index=True,
            column_config={"date": st.column_config.DateColumn("Data", format="DD-MM-YYYY"), "amount": st.column_config.NumberColumn("Importo", format="€ %.2f"), "note": st.column_config.TextColumn("Note")})
    else:
        st.info("Nessun movimento ancora registrato.")

# --- TAB 5: GESTIONE LIQUIDITA' ---
with tab5:
    st.subheader("Gestione Liquidità Cash")
    st.info("Di default, la liquidità è calcolata automaticamente. Se vuoi, puoi **sovrascrivere** questo calcolo con un valore manuale (es. il saldo del tuo conto corrente).")
    df_settings = get_data("settings")
    current_liquidity = 0.0
    is_manual_mode = False
    if not df_settings.empty:
        liquidity_setting = df_settings[df_settings['key'] == 'manual_liquidity']
        if not liquidity_setting.empty:
            current_liquidity = float(liquidity_setting['value'].iloc[0])
            if current_liquidity > 0: is_manual_mode = True
    if is_manual_mode: st.success(f"Modalità Attiva: **Manuale**. Valore attuale: **€ {current_liquidity:,.2f}**")
    else: st.info("Modalità Attiva: **Automatica**. La liquidità è calcolata da entrate, uscite e investimenti.")
    st.divider()
    st.subheader("Imposta Valore Manuale")
    manual_liquidity_input = st.number_input("Importo da impostare (€)", value=current_liquidity if is_manual_mode else 0.0, min_value=0.0, step=100.0, format="%.2f")
    col1, col2 = st.columns(2)
    if col1.button("💾 Salva Valore Manuale", type="primary"):
        new_setting = pd.DataFrame([{'key': 'manual_liquidity', 'value': str(manual_liquidity_input)}])
        df_existing_settings = get_data("settings")
        if not df_existing_settings.empty: df_existing_settings = df_existing_settings[df_existing_settings['key'] != 'manual_liquidity']
        df_final_settings = pd.concat([df_existing_settings, new_setting], ignore_index=True)
        save_data(df_final_settings, "settings", method='replace')
        st.success(f"✅ Liquidità manuale impostata a € {manual_liquidity_input:,.2f}")
        st.rerun()
    if col2.button("🗑️ Elimina e Usa Calcolo Automatico"):
        df_existing_settings = get_data("settings")
        if not df_existing_settings.empty:
            df_final_settings = df_existing_settings[df_existing_settings['key'] != 'manual_liquidity']
            save_data(df_final_settings, "settings", method='replace')
            st.success("✅ Impostazione manuale rimossa. L'app userà il calcolo automatico.")
            st.rerun()
        else:
            st.info("Nessuna impostazione manuale da rimuovere.")

# --- TAB 6: GESTIONE ALLOCAZIONE ASSET ---
with tab6:
    st.subheader("Scarica e Modifica Dati di Allocazione (X-Ray)")
    st.caption("Scarica i dati da JustETF, modificali se necessario e salvali.")
    df_map = get_data("mapping")
    df_trans = get_data("transactions")
    df_alloc = get_data("asset_allocation")
    if df_map.empty or df_trans.empty:
        st.warning("Mancano le transazioni o la mappatura. Completa i passaggi precedenti.")
    else:
        df_full = df_trans.merge(df_map, on='isin', how='left')
        holdings = df_full.groupby(['product', 'ticker', 'isin']).agg({'quantity':'sum'}).reset_index()
        view = holdings[holdings['quantity'] > 0.001].copy()
        options = view.apply(lambda x: f"{x['product']} ({x['ticker']})", axis=1).unique()
        
        st.divider()
        st.subheader("1. Scarica Nuovi Dati")
        col_sel, col_btn = st.columns([3, 1])
        selected_option = col_sel.selectbox("Seleziona un asset da analizzare:", options, key="asset_selector_alloc")
        
        if col_btn.button("⚡ Analizza Asset (JustETF)", type="primary"):
            with st.spinner("Scraping in corso..."):
                sel_ticker = selected_option.split('(')[-1].replace(')', '')
                sel_isin = view[view['ticker'] == sel_ticker].iloc[0]['isin']
                geo, sec = fetch_justetf_allocation_robust(sel_isin)
                if geo or sec:
                    st.session_state.scraped_data = {'ticker': sel_ticker, 'geo': geo, 'sec': sec}
                    st.success(f"Dati per {sel_ticker} scaricati! Vai al punto 2 per verificare e salvare.")
                else:
                    st.session_state.scraped_data = None
                    st.error("Nessun dato di allocazione trovato automaticamente per questo ISIN.")
        
        # --- SEZIONE DI VERIFICA E SALVATAGGIO ---
        if st.session_state.scraped_data:
            st.divider()
            st.subheader("2. Verifica e Salva Dati")
            data = st.session_state.scraped_data
            st.info(f"Dati scaricati per **{data['ticker']}**. Puoi modificarli prima di salvare.")
            
            with st.form("verify_and_save_form"):
                c1, c2 = st.columns(2)
                geo_text = c1.text_area("JSON Geografico", value=json.dumps(data['geo'], indent=2, ensure_ascii=False), height=300)
                sec_text = c2.text_area("JSON Settoriale", value=json.dumps(data['sec'], indent=2, ensure_ascii=False), height=300)
                
                submitted = st.form_submit_button("💾 Salva Dati nel Database", type="primary")
                if submitted:
                    try:
                        final_geo = json.loads(geo_text)
                        final_sec = json.loads(sec_text)
                        save_allocation_json(data['ticker'], final_geo, final_sec)
                        st.success(f"Dati di allocazione per {data['ticker']} salvati con successo!")
                        st.session_state.scraped_data = None # Pulisce lo stato
                        st.rerun()
                    except json.JSONDecodeError:
                        st.error("Errore nel formato JSON. Controlla la sintassi (es. virgole, parentesi).")
                    except Exception as e:
                        st.error(f"Errore durante il salvataggio: {e}")

        st.divider()
        st.subheader("3. Modifica Dati Esistenti")
        if not df_alloc.empty:
            alloc_tickers = df_alloc['ticker'].unique()
            ticker_to_edit = st.selectbox("Seleziona un asset da modificare:", alloc_tickers)
            if ticker_to_edit:
                record = df_alloc[df_alloc['ticker'] == ticker_to_edit].iloc[0]
                with st.form("edit_alloc_form"):
                    st.write(f"**Dati per: {ticker_to_edit}**")
                    c1_edit, c2_edit = st.columns(2)
                    try:
                        geo_db = record['geography_json'] if isinstance(record['geography_json'], dict) else json.loads(record['geography_json'] or '{}')
                        sec_db = record['sector_json'] if isinstance(record['sector_json'], dict) else json.loads(record['sector_json'] or '{}')
                    except:
                        geo_db, sec_db = {}, {}
                    
                    # Assegna chiavi uniche per accedere ai valori del form
                    geo_key = f"geo_edit_{ticker_to_edit}"
                    sec_key = f"sec_edit_{ticker_to_edit}"

                    c1_edit.text_area("JSON Geografico Esistente", value=json.dumps(geo_db, indent=2, ensure_ascii=False), height=300, key=geo_key)
                    c2_edit.text_area("JSON Settoriale Esistente", value=json.dumps(sec_db, indent=2, ensure_ascii=False), height=300, key=sec_key)
                    
                    submitted_edit = st.form_submit_button("💾 Aggiorna Dati", type="primary")
                    if submitted_edit:
                        try:
                            # FIX: Legge i dati modificati dallo stato del widget (session_state)
                            geo_dict_edit = json.loads(st.session_state[geo_key])
                            sec_dict_edit = json.loads(st.session_state[sec_key])
                            
                            save_allocation_json(ticker_to_edit, geo_dict_edit, sec_dict_edit)
                            st.success(f"Dati di allocazione per {ticker_to_edit} aggiornati!")
                            st.rerun()
                        except json.JSONDecodeError:
                            st.error("Errore nel formato JSON. Controlla la sintassi.")
        else:
            st.info("Nessun dato di allocazione ancora salvato nel database.")