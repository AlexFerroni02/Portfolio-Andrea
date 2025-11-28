import streamlit as st
import pandas as pd
from utils import parse_degiro_csv, generate_id, get_data, save_data, sync_prices

st.set_page_config(page_title="Gestione Dati", page_icon="📂")
st.title("📂 Gestione Database")

df_trans = get_data("transactions")
df_map = get_data("mapping")

# --- SEZIONE 1: IMPORTAZIONE ---
st.header("1. Importa Transazioni")
uploaded_file = st.file_uploader("Carica Transactions.csv", type=['csv'])

if uploaded_file and st.button("Importa"):
    ndf = parse_degiro_csv(uploaded_file)
    rows = []
    exist = df_trans['id'].tolist() if not df_trans.empty else []
    count = 0
    
    for idx, r in ndf.iterrows():
        if pd.isna(r['ISIN']): continue
        # Usa l'indice (idx) per evitare duplicati su ordini spezzati
        tid = generate_id(r, idx)
        if tid not in exist:
            val_reale = r['Totale'] if r['Totale'] != 0 else r['Valore']
            rows.append({
                'id': tid, 'date': r['Data'].strftime('%Y-%m-%d'),
                'product': r['Prodotto'], 'isin': r['ISIN'],
                'quantity': r['Quantità'], 'local_value': val_reale,
                'fees': r['Costi di transazione'], 'currency': 'EUR'
            })
            exist.append(tid)
            count += 1
    
    if rows:
        save_data(pd.concat([df_trans, pd.DataFrame(rows)], ignore_index=True), "transactions")
        st.success(f"✅ Importate {count} nuove righe.")
        st.rerun() # Ricarica per vedere subito se mancano ticker
    else:
        st.info("Nessuna nuova transazione trovata.")

st.divider()

# --- SEZIONE 2: MAPPING MANUALE (Quello che volevi) ---
st.header("2. Associa Ticker (Manuale)")

if not df_trans.empty:
    # 1. Trova tutti gli ISIN che hai nelle transazioni
    all_isins = df_trans['isin'].unique()
    
    # 2. Trova quelli che hai già mappato nel DB
    mapped_isins = df_map['isin'].unique() if not df_map.empty else []
    
    # 3. Trova la differenza (quelli che mancano)
    missing = [i for i in all_isins if i not in mapped_isins]
    
    if missing:
        st.warning(f"⚠️ Ci sono {len(missing)} ETF senza Ticker associato!")
        
        with st.form("manual_mapping_form"):
            new_maps = []
            st.write("Inserisci il Ticker Yahoo (es. SWDA.MI) per gli ETF nuovi:")
            
            for m in missing:
                # Recupera il nome del prodotto per aiutarti a capire cos'è
                prod_name = df_trans[df_trans['isin']==m]['product'].iloc[0]
                
                col1, col2 = st.columns([3, 1])
                col1.caption(f"**{prod_name}** ({m})")
                val = col2.text_input("Ticker", key=m, placeholder="es. AGGH.MI")
                
                if val:
                    new_maps.append({'isin': m, 'ticker': val.strip()})
            
            if st.form_submit_button("Salva Associazioni"):
                if new_maps:
                    df_new = pd.DataFrame(new_maps)
                    # Aggiungi ai vecchi
                    df_final_map = pd.concat([df_map, df_new], ignore_index=True)
                    save_data(df_final_map, "mapping")
                    st.success("✅ Mapping salvato!")
                    st.rerun()
    else:
        st.success("✅ Tutti i tuoi ETF hanno un Ticker associato.")

st.divider()

# --- SEZIONE 3: AGGIORNAMENTO PREZZI ---
st.header("3. Aggiorna Mercato")

if st.button("🔄 Scarica Prezzi da Yahoo"):
    if not df_map.empty:
        with st.spinner("Scaricamento in corso..."):
            n = sync_prices(df_map['ticker'].unique().tolist())
        st.success(f"Aggiornati {n} prezzi.")
    else:
        st.warning("Mapping vuoto. Associa prima i ticker.")