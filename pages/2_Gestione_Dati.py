import streamlit as st
import pandas as pd
from datetime import date, datetime
from utils import get_data, save_data, parse_degiro_csv, generate_id, sync_prices, make_sidebar

st.set_page_config(page_title="Gestione Dati", page_icon="📂", layout="wide")
make_sidebar()
st.title("📂 Gestione Database")

# Definiamo le categorie standard in un unico posto
CATEGORIE_ASSET = ["Azionario", "Obbligazionario", "Gold", "Liquidità"]

tab1, tab2, tab3, tab4 = st.tabs(["📥 Importa CSV", "🔗 Mappatura Ticker", "🔄 Aggiorna Prezzi", "💸 Movimenti Bilancio"])

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
                    rows_to_add.append({
                        'id': tid, 'date': r['Data'], 'product': r.get('Prodotto',''), 
                        'isin': r.get('ISIN',''), 'quantity': r.get('Quantità',0), 
                        'local_value': val, 'fees': r.get('Costi di transazione',0), 'currency': 'EUR'
                    })
                    existing_ids.add(tid)
            if rows_to_add:
                new_df = pd.DataFrame(rows_to_add)
                save_data(new_df, "transactions", method='append')
                st.success(f"✅ Importate {len(rows_to_add)} nuove transazioni!")
            else:
                st.info("Nessuna nuova transazione trovata.")

# --- TAB 2: MAPPING (AGGIORNATO) ---
with tab2:
    st.subheader("Mappatura Asset")
    df_map = get_data("mapping")
    st.dataframe(df_map, use_container_width=True)
    
    st.subheader("Aggiungi/Modifica Mappatura")
    with st.form("add_map"):
        c1, c2, c3 = st.columns(3)
        isin = c1.text_input("ISIN (es. IE00B4L5Y983)")
        ticker = c2.text_input("Ticker Yahoo (es. SWDA.MI)")
        category = c3.selectbox("Categoria Asset", CATEGORIE_ASSET)
        
        if st.form_submit_button("Salva Mappatura"):
            if isin and ticker and category:
                new = pd.DataFrame([{'isin': isin.strip(), 'ticker': ticker.strip(), 'category': category}])
                df_final = pd.concat([df_map, new], ignore_index=True).drop_duplicates(subset=['isin'], keep='last')
                save_data(df_final, "mapping", method='replace')
                st.success("Salvato!")
                st.rerun()

# --- TAB 3: PREZZI ---
with tab3:
    st.write("Scarica gli ultimi prezzi di chiusura da Yahoo Finance **solo per gli asset che possiedi**.")
    if st.button("Avvia Sincronizzazione Prezzi"):
        df_trans = get_data("transactions")
        df_map = get_data("mapping")
        if not df_map.empty and not df_trans.empty:
            n = sync_prices(df_trans, df_map)
            if n > 0: st.success(f"✅ Aggiornamento completato: {n} nuovi prezzi salvati.")
            else: st.info("Tutti i prezzi per gli asset posseduti sono già aggiornati.")
        else:
            st.error("Database transazioni o mappatura vuoto. Impossibile aggiornare i prezzi.")

# --- TAB 4: MOVIMENTI BILANCIO ---
with tab4:
    st.header("➕ Aggiungi Entrate o Uscite")
    CATEGORIE_ENTRATE = ["Stipendio", "Bonus", "Regali", "Dividendi", "Rimborso", "Altro"]
    CATEGORIE_USCITE = ["Affitto/Casa", "Spesa Alimentare", "Ristoranti/Svago", "Trasporti", "Viaggi", "Salute", "Shopping", "Bollette", "Altro"]
    col_type, _ = st.columns([1, 3])
    f_type = col_type.radio("Tipo Movimento:", ["Uscita", "Entrata"], horizontal=True, key="budget_type")
    lista_cat = CATEGORIE_ENTRATE if f_type == "Entrata" else CATEGORIE_USCITE
    with st.form("budget_form", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        f_date = col1.date_input("Data", date.today())
        f_cat = col2.selectbox("Categoria", lista_cat)
        f_amount = col3.number_input("Importo (€)", min_value=0.0, step=10.0, format="%.2f")
        f_note = st.text_input("Note (opzionale)")
        if st.form_submit_button("💾 Salva Movimento", type="primary"):
            if f_amount > 0:
                new_entry = pd.DataFrame([{'date': pd.to_datetime(f_date), 'type': f_type, 'category': f_cat, 'amount': f_amount, 'note': f_note}])
                save_data(new_entry, "budget", method='append')
                st.success(f"✅ Salvato: {f_cat} - € {f_amount}")
            else:
                st.warning("Inserisci un importo maggiore di 0.")
    st.divider()
    st.subheader("Ultimi Movimenti Inseriti")
    df_budget_display = get_data("budget")
    if not df_budget_display.empty:
        df_budget_display['date'] = pd.to_datetime(df_budget_display['date'])
        st.dataframe(df_budget_display.sort_values('date', ascending=False).head(10), use_container_width=True, hide_index=True,
            column_config={"date": st.column_config.DateColumn("Data", format="DD-MM-YYYY"), "amount": st.column_config.NumberColumn("Importo", format="€ %.2f")})
    else:
        st.info("Nessun movimento ancora registrato.")