import streamlit as st
import pandas as pd
from datetime import date, datetime
from utils import get_data, save_data, parse_degiro_csv, generate_id, sync_prices, make_sidebar

st.set_page_config(page_title="Gestione Dati", page_icon="📂", layout="wide")
make_sidebar()
st.title("📂 Gestione Database")

# Inizializza la lista temporanea per i movimenti se non esiste
if 'pending_entries' not in st.session_state:
    st.session_state.pending_entries = []

# Aggiunto Tab "Movimenti Bilancio"
tab1, tab2, tab3, tab4 = st.tabs(["📥 Importa CSV", "🔗 Mappatura Ticker", "🔄 Aggiorna Prezzi", "💸 Movimenti Bilancio"])

# --- TAB 1: IMPORT ---
with tab1:
    st.write("Carica il file `Transactions.csv` di DEGIRO.")
    up = st.file_uploader("Upload CSV", type=['csv'])
    if up and st.button("Importa Transazioni"):
        ndf = parse_degiro_csv(up)
        df_trans = get_data("transactions")
        exist = df_trans['id'].tolist() if not df_trans.empty else []
        rows = []
        c = 0
        for idx, r in ndf.iterrows():
            if pd.isna(r.get('ISIN')): continue
            tid = generate_id(r, idx)
            if tid not in exist:
                val = r.get('Totale', 0) if r.get('Totale', 0) != 0 else r.get('Valore', 0)
                rows.append({
                    'id': tid, 'date': r['Data'].strftime('%Y-%m-%d'),
                    'product': r.get('Prodotto',''), 'isin': r.get('ISIN',''),
                    'quantity': r.get('Quantità',0), 'local_value': val,
                    'fees': r.get('Costi di transazione',0), 'currency': 'EUR'
                })
                exist.append(tid)
                c += 1
        if rows:
            new_df = pd.concat([df_trans, pd.DataFrame(rows)], ignore_index=True) if not df_trans.empty else pd.DataFrame(rows)
            save_data(new_df, "transactions")
            st.success(f"✅ Importate {c} nuove transazioni!")
        else:
            st.info("Nessuna nuova transazione trovata.")

# --- TAB 2: MAPPING ---
with tab2:
    df_map = get_data("mapping")
    st.dataframe(df_map, use_container_width=True)
    
    with st.form("add_map"):
        c1, c2 = st.columns(2)
        isin = c1.text_input("ISIN (es. IE00B4L5Y983)")
        ticker = c2.text_input("Ticker Yahoo (es. SWDA.MI)")
        if st.form_submit_button("Salva Mappatura"):
            if isin and ticker:
                new = pd.DataFrame([{'isin': isin.strip(), 'ticker': ticker.strip()}])
                df_final = pd.concat([df_map, new], ignore_index=True).drop_duplicates(subset=['isin'], keep='last')
                save_data(df_final, "mapping")
                st.success("Salvato! Ricarica la pagina.")
                st.rerun()

# --- TAB 3: PREZZI ---
with tab3:
    st.write("Scarica gli ultimi prezzi di chiusura da Yahoo Finance.")
    if st.button("Avvia Sincronizzazione Prezzi"):
        df_map = get_data("mapping")
        if not df_map.empty:
            tickers = df_map['ticker'].unique().tolist()
            n = sync_prices(tickers)
            st.success(f"✅ Aggiornamento completato: {n} nuovi prezzi salvati.")
        else:
            st.error("Nessuna mappatura trovata. Configura prima i ticker.")

# --- TAB 4: MOVIMENTI BILANCIO (BATCH MODE) ---
with tab4:
    st.header("➕ Aggiungi Entrate o Uscite")
    st.caption("Inserisci più movimenti e poi premi 'Salva Tutto su Cloud' per inviarli in una volta sola.")
    
    CATEGORIE_ENTRATE = ["Stipendio", "Bonus", "Regali", "Dividendi", "Rimborso", "Altro"]
    CATEGORIE_USCITE = ["Affitto/Casa", "Spesa Alimentare", "Ristoranti/Svago", "Trasporti", "Viaggi", "Salute", "Shopping", "Bollette", "Altro"]
    
    # 1. FORM DI INSERIMENTO (SOLO LOCALE)
    col_type, _ = st.columns([1, 3])
    with col_type:
        f_type = st.radio("Tipo Movimento:", ["Uscita", "Entrata"], horizontal=True)
    
    lista_cat = CATEGORIE_ENTRATE if f_type == "Entrata" else CATEGORIE_USCITE

    with st.form("budget_form_batch", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        f_date = col1.date_input("Data", date.today())
        f_cat = col2.selectbox("Categoria", lista_cat)
        f_amount = col3.number_input("Importo (€)", min_value=0.0, step=10.0, format="%.2f")
        f_note = st.text_input("Note (opzionale)")
        
        # Questo bottone ora aggiunge solo alla lista temporanea
        if st.form_submit_button("⬇️ Aggiungi alla Coda"):
            if f_amount > 0:
                st.session_state.pending_entries.append({
                    'date': f_date.strftime('%Y-%m-%d'),
                    'type': f_type,
                    'category': f_cat,
                    'amount': f_amount,
                    'note': f_note
                })
                st.toast(f"Aggiunto: {f_cat} - € {f_amount}")
            else:
                st.warning("Inserisci un importo maggiore di 0.")

    st.divider()

    # 2. AREA DI SOSTA (VISUALIZZA, MODIFICA, ELIMINA)
    if st.session_state.pending_entries:
        st.subheader(f"🛒 Movimenti in attesa di salvataggio ({len(st.session_state.pending_entries)})")
        
        # Creiamo il DataFrame dalla lista in memoria
        df_pending = pd.DataFrame(st.session_state.pending_entries)
        
        # Aggiungiamo la colonna per la spunta "Elimina"
        df_pending.insert(0, "Elimina", False)
        
        # Editor Interattivo
        edited_pending = st.data_editor(
            df_pending, 
            column_config={
                "Elimina": st.column_config.CheckboxColumn("Elimina?", default=False),
                "date": st.column_config.DateColumn("Data", format="DD-MM-YYYY"),
                "amount": st.column_config.NumberColumn("Importo", format="€ %.2f"),
                "type": "Tipo",
                "category": "Categoria",
                "note": "Note"
            },
            # Blocchiamo le altre colonne per evitare modifiche accidentali mentre si cancella
            # Se vuoi poter modificare anche i dati, togli le colonne da questa lista
            disabled=["date", "type", "category", "amount", "note"],
            hide_index=True,
            use_container_width=True,
            key="editor_pending"
        )

        # --- LOGICA DI ELIMINAZIONE ---
        # Controlliamo se ci sono righe spuntate
        rows_to_delete = edited_pending[edited_pending["Elimina"] == True]
        
        if not rows_to_delete.empty:
            st.warning(f"Vuoi rimuovere {len(rows_to_delete)} righe dalla coda?")
            if st.button("🗑️ Rimuovi Selezionati dalla Coda"):
                # Filtriamo tenendo solo quelle NON spuntate
                df_kept = edited_pending[edited_pending["Elimina"] == False]
                # Rimuoviamo la colonna "Elimina" prima di salvare nello stato
                df_kept = df_kept.drop(columns=["Elimina"])
                # Aggiorniamo lo stato
                st.session_state.pending_entries = df_kept.to_dict('records')
                st.rerun()

        st.divider()

        # --- PULSANTI DI AZIONE ---
        col_save, col_clear = st.columns([1, 4])
        
        with col_save:
            # Il pulsante di salvataggio appare solo se non stai cercando di cancellare cose
            if rows_to_delete.empty:
                if st.button("☁️ SALVA TUTTO SU CLOUD", type="primary"):
                    with st.spinner("Salvataggio in corso su Google Sheets..."):
                        # 1. Carica dati attuali dal cloud
                        df_budget = get_data("budget")
                        
                        # 2. Prepara i nuovi dati (togliendo la colonna Elimina se presente)
                        df_new = edited_pending.drop(columns=["Elimina"], errors='ignore')
                        
                        # 3. Unisci
                        if df_budget.empty:
                            df_final = df_new
                        else:
                            df_final = pd.concat([df_budget, df_new], ignore_index=True)
                        
                        # 4. Pulizia Date
                        if 'date' in df_final.columns:
                            df_final['date'] = pd.to_datetime(df_final['date']).dt.strftime('%Y-%m-%d')
                        
                        # 5. Salva
                        save_data(df_final, "budget")
                        
                        # 6. Pulisci la coda
                        st.session_state.pending_entries = []
                        st.success("✅ Tutti i movimenti sono stati salvati!")
                        st.rerun()
        
        with col_clear:
            if st.button("❌ Svuota Intera Coda"):
                st.session_state.pending_entries = []
                st.rerun()
    else:
        st.info("La coda è vuota. Usa il form sopra per aggiungere movimenti.")