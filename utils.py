import streamlit as st
import pandas as pd
import yfinance as yf
import hashlib
from datetime import date, timedelta, datetime

# --- CONNESSIONE AL DATABASE (NEON/POSTGRESQL) ---
@st.cache_resource
def get_db_connection():
    """Stabilisce la connessione al DB usando i secrets di Streamlit. Questa funzione è cachata per l'intera sessione."""
    return st.connection("postgresql", type="sql")

# --- LETTURA DATI (CON CACHE STRUTTURALE) ---
@st.cache_data
def get_data(table_name):
    """
    Legge un'intera tabella dal database.
    I dati vengono cachati. La cache viene invalidata esplicitamente da save_data().
    """
    try:
        conn = get_db_connection()
        # Usiamo un ttl basso qui per sicurezza, ma l'invalidazione principale avviene in save_data
        df = conn.query(f'SELECT * FROM "{table_name}";', ttl=5) 
        return df
    except Exception:
        return pd.DataFrame()

# --- SALVATAGGIO DATI (CON INVALIDAZIONE CACHE) ---
def save_data(df, table_name, method='replace'):
    """
    Salva un DataFrame in una tabella.
    - method='replace': Sovrascrive l'intera tabella (default).
    - method='append': Aggiunge le nuove righe in fondo alla tabella.
    """
    try:
        conn = get_db_connection()
        df.to_sql(name=table_name, con=conn.engine, if_exists=method, index=False)
        
        # Questa riga ora funziona perché get_data ha di nuovo il decoratore @st.cache_data
        get_data.clear()
        
    except Exception as e:
        st.error(f"Errore durante il salvataggio della tabella '{table_name}': {e}")

# --- FUNZIONI DI LOGICA (INVARIATE) ---

def parse_degiro_csv(file):
    df = pd.read_csv(file)
    cols = ['Quantità', 'Quotazione', 'Valore', 'Costi di transazione', 'Totale']
    for c in cols:
        if c in df.columns:
            df[c] = df[c].astype(str).str.replace(',', '.').apply(pd.to_numeric, errors='coerce').fillna(0)
    if 'Data' in df.columns:
        df['Data'] = pd.to_datetime(df['Data'], format='%d-%m-%Y', errors='coerce').dt.normalize()
    if 'Costi di transazione' in df.columns:
        df['Costi di transazione'] = df['Costi di transazione'].abs()
    return df

def generate_id(row, index):
    d_str = row['Data'].strftime('%Y-%m-%d') if pd.notna(row['Data']) else ""
    raw = f"{index}{d_str}{row.get('Ora','')}{row.get('ISIN','')}{row.get('Quantità','')}{row.get('Valore','')}"
    return hashlib.md5(raw.encode()).hexdigest()

def sync_prices(tickers):
    if not tickers: return 0
    
    # Usiamo il metodo 'append' per efficienza
    df_prices_all = get_data("prices")
    if not df_prices_all.empty:
        df_prices_all['date'] = pd.to_datetime(df_prices_all['date'], errors='coerce').dt.normalize()
        df_prices_all = df_prices_all.dropna(subset=['date'])

    new_data = []
    bar = st.progress(0, text="Sincronizzazione prezzi...")
    for i, t in enumerate(tickers):
        start_date = "2020-01-01"
        if not df_prices_all.empty:
            exist = df_prices_all[df_prices_all['ticker'] == t]
            if not exist.empty:
                last = exist['date'].max()
                if pd.notna(last) and last.date() < (date.today() - timedelta(days=1)):
                    start_date = (last + timedelta(days=1)).strftime('%Y-%m-%d')
                elif pd.notna(last):
                    bar.progress((i + 1) / len(tickers), text=f"Prezzi per {t} già aggiornati.")
                    continue
        try:
            hist = yf.download(t, start=start_date, progress=False)
            if not hist.empty:
                closes = hist['Close']
                for d, v in closes.items():
                    if pd.notna(v):
                        new_data.append({'ticker': t, 'date': d.strftime('%Y-%m-%d'), 'close_price': float(v)})
        except Exception:
            pass
        bar.progress((i + 1) / len(tickers), text=f"Scaricati prezzi per {t}")
    bar.empty()
    
    if new_data:
        df_new = pd.DataFrame(new_data)
        # Sovrascriviamo l'intera tabella dei prezzi per semplicità, dopo averla aggiornata
        df_combined = pd.concat([df_prices_all, df_new], ignore_index=True)
        df_combined = df_combined.drop_duplicates(subset=['ticker', 'date'], keep='last')
        save_data(df_combined, "prices", method='replace')
        return len(df_new)
    
    return 0

def color_pnl(val):
    try:
        v = float(str(val).strip('%'))
        color = '#d4edda' if v >= 0 else '#f8d7da'
        text_color = '#155724' if v >= 0 else '#721c24'
        return f'background-color: {color}; color: {text_color}'
    except:
        return ''
    
def style_chart_for_mobile(fig):
    """
    Rende il grafico perfetto sia su Mobile che Desktop.
    - Mobile: La legenda sopra non ruba spazio, i margini sono zero.
    - Desktop: La legenda sopra è elegante, il grafico è largo.
    """
    fig.update_layout(
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        margin=dict(l=10, r=10, t=40, b=10),
        hovermode="x unified",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig

def make_sidebar():
    with st.sidebar:
        st.header("Navigazione")
        st.page_link("app.py", label="Dashboard", icon="🏠")
        st.page_link("pages/2_Gestione_Dati.py", label="Gestione Dati", icon="📂")
        st.page_link("pages/3_Benchmark.py", label="Benchmark", icon="⚖️")
        st.page_link("pages/4_Bilancio.py", label="Bilancio", icon="💰")
        st.divider()