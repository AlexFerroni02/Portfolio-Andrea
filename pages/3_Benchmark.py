import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from utils import get_data, make_sidebar

st.set_page_config(page_title="Benchmark", layout="wide", page_icon="⚖️")
make_sidebar()
st.title("⚖️ Sfida il Mercato")

# 1. CARICAMENTO DATI
with st.spinner("Caricamento dati..."):
    df_trans = get_data("transactions")
    df_map = get_data("mapping")
    df_prices = get_data("prices")

if df_trans.empty:
    st.warning("⚠️ Carica prima i dati nella pagina Gestione.")
    st.stop()

# Preparazione dati
try:
    df_trans['date'] = pd.to_datetime(df_trans['date'], errors='coerce').dt.normalize()
    if not df_prices.empty:
        df_prices['date'] = pd.to_datetime(df_prices['date'], errors='coerce').dt.normalize()
except Exception as e:
    st.error(f"Errore conversione date: {e}")
    st.stop()

df_full = df_trans.merge(df_map, on='isin', how='left')

# 2. SCELTA DEL BENCHMARK
col1, col2 = st.columns([1, 3])
with col1:
    bench_ticker = st.text_input("Ticker Yahoo", value="SWDA.MI")
with col2:
    st.info("Simulazione Shadow: Ogni euro investito nel tuo portafoglio viene replicato virtualmente sul Benchmark nello stesso istante.")

# 3. SCARICO DATI BENCHMARK
start_date = df_trans['date'].min()
end_date = pd.Timestamp.today()

if bench_ticker:
    with st.spinner(f"Calcolo simulazione su {bench_ticker}..."):
        try:
            bench_hist = yf.download(bench_ticker, start=start_date, end=end_date, progress=False)
            
            # Pulizia dati Yahoo
            if isinstance(bench_hist.columns, pd.MultiIndex):
                bench_hist = bench_hist['Close']
            elif 'Close' in bench_hist.columns:
                bench_hist = bench_hist[['Close']]
            
            if bench_hist.empty:
                st.error(f"Nessun dato trovato per '{bench_ticker}'.")
                st.stop()
            
            if isinstance(bench_hist, pd.DataFrame):
                bench_hist = bench_hist.iloc[:, 0]
            
            # Normalizzazione e Riempimento Buchi (Cruciale per non perdere soldi nei festivi)
            bench_hist.index = pd.to_datetime(bench_hist.index).normalize()
            full_idx = pd.date_range(start=bench_hist.index.min(), end=bench_hist.index.max(), freq='D')
            bench_hist = bench_hist.reindex(full_idx).ffill()

        except Exception as e:
            st.error(f"Errore download benchmark: {e}")
            st.stop()

    # 4. SIMULAZIONE (Shadow Portfolio)
    timeline = pd.date_range(start=start_date, end=end_date, freq='D').normalize()
    
    my_val_history = []
    bench_val_history = []
    
    # Pivot dei tuoi prezzi
    pivot_user = pd.DataFrame()
    if not df_prices.empty:
        pivot_user = df_prices.pivot_table(index='date', columns='ticker', values='close_price', aggfunc='last').sort_index().ffill()
    
    trans_grouped = df_full.groupby('date')
    
    user_qty = {} 
    bench_qty = 0 
    
    # Variabili verifica
    tot_invested_real = 0.0
    tot_invested_bench = 0.0

    for d in timeline:
        daily_cash = 0
        
        # A. Gestione Movimenti Reali
        if d in trans_grouped.groups:
            moves = trans_grouped.get_group(d)
            for _, row in moves.iterrows():
                tk = row['ticker']
                if pd.notna(tk):
                    user_qty[tk] = user_qty.get(tk, 0) + row['quantity']
                
                # Calcola soldi spesi (local_value negativo = spesa)
                cash = -row['local_value']
                daily_cash += cash
                tot_invested_real += cash

        # B. Investimento Virtuale Benchmark
        if daily_cash != 0:
            # Grazie al ffill() fatto sopra, .asof() troverà sempre un prezzo valido
            try:
                idx = bench_hist.index.asof(d)
                if pd.notna(idx):
                    p_bench = bench_hist.at[idx]
                    if pd.notna(p_bench) and p_bench > 0:
                        quotes_bought = daily_cash / p_bench
                        bench_qty += quotes_bought
                        tot_invested_bench += daily_cash
            except: pass

        # C. Valutazione Giornaliera
        
        # Valore Mio
        val_user = 0
        for tk, q in user_qty.items():
            if q > 0.001 and tk in pivot_user.columns:
                try:
                    idx = pivot_user.index.asof(d)
                    if pd.notna(idx):
                        p = pivot_user.at[idx, tk]
                        if pd.notna(p): val_user += q * p
                except: pass
        
        # Valore Benchmark
        val_bench = 0
        try:
            idx = bench_hist.index.asof(d)
            if pd.notna(idx):
                p_bench = bench_hist.at[idx]
                if pd.notna(p_bench): val_bench = bench_qty * p_bench
        except: pass
        
        my_val_history.append(val_user)
        bench_val_history.append(val_bench)

    # 5. RISULTATI E GRAFICI
    final_user = my_val_history[-1]
    final_bench = bench_val_history[-1]
    diff = final_user - final_bench
    
    st.divider()
    
    # Caption per spiegare la differenza
    st.caption(f"ℹ️ Nota: Il Benchmark ha investito **€ {tot_invested_bench:,.2f}** (Soldi Freschi). La Dashboard segna **€ {tot_invested_real:,.2f}** (Costo Attuale). La differenza è il profitto che hai già realizzato e reinvestito.")
    
    k1, k2, k3 = st.columns(3)
    k1.metric("Il Tuo Portafoglio", f"€ {final_user:,.2f}")
    k2.metric(f"Benchmark ({bench_ticker})", f"€ {final_bench:,.2f}")
    k3.metric("Alpha (Differenza)", f"€ {diff:,.2f}", 
              delta=f"{((final_user - final_bench)/final_bench)*100:.2f}%" if final_bench else "0%")

    # DataFrame per i grafici
    df_chart = pd.DataFrame({'Data': timeline, 'Tu': my_val_history, 'Benchmark': bench_val_history})
    # Pulizia giorni vuoti iniziali
    df_chart = df_chart[(df_chart['Tu'] > 0) | (df_chart['Benchmark'] > 0)]

    # --- GRAFICO 1: PERFORMANCE ---
    st.subheader("📈 Gara di Rendimento")
    fig1 = go.Figure()
    fig1.add_trace(go.Scatter(x=df_chart['Data'], y=df_chart['Tu'], name='Il Tuo Portafoglio', line=dict(color='#00CC96', width=3)))
    fig1.add_trace(go.Scatter(x=df_chart['Data'], y=df_chart['Benchmark'], name=f'Benchmark ({bench_ticker})', line=dict(color='#A0A0A0', width=2, dash='dot')))
    fig1.update_layout(title="Valore nel Tempo (€)", hovermode="x unified", margin=dict(l=0,r=0))
    st.plotly_chart(fig1, use_container_width=True)

    # --- GRAFICO 2: DRAWDOWN (RISCHIO) ---
    st.subheader("🌊 Analisi del Rischio (Drawdown)")
    st.caption("Quanto perdi dai massimi? L'area rossa indica i tuoi crolli.")

    # Calcolo Drawdown
    df_chart['Tu_Max'] = df_chart['Tu'].cummax()
    df_chart['Bench_Max'] = df_chart['Benchmark'].cummax()
    
    # Evita divisione per zero
    df_chart['Tu_DD'] = 0.0
    mask_tu = df_chart['Tu_Max'] > 0
    df_chart.loc[mask_tu, 'Tu_DD'] = ((df_chart.loc[mask_tu, 'Tu'] - df_chart.loc[mask_tu, 'Tu_Max']) / df_chart.loc[mask_tu, 'Tu_Max']) * 100

    df_chart['Bench_DD'] = 0.0
    mask_bench = df_chart['Bench_Max'] > 0
    df_chart.loc[mask_bench, 'Bench_DD'] = ((df_chart.loc[mask_bench, 'Benchmark'] - df_chart.loc[mask_bench, 'Bench_Max']) / df_chart.loc[mask_bench, 'Bench_Max']) * 100
    
    fig2 = go.Figure()
    # Tuo Drawdown (Rosso Pieno)
    fig2.add_trace(go.Scatter(x=df_chart['Data'], y=df_chart['Tu_DD'], name='Il Tuo Drawdown', fill='tozeroy', line=dict(color='#EF553B', width=1)))
    # Benchmark Drawdown (Linea Grigia)
    fig2.add_trace(go.Scatter(x=df_chart['Data'], y=df_chart['Bench_DD'], name='Benchmark', line=dict(color='#A0A0A0', width=1, dash='dot')))
    
    fig2.update_layout(title="Perdita dai Massimi (%)", hovermode="x unified", margin=dict(l=0,r=0), yaxis=dict(ticksuffix="%"))
    st.plotly_chart(fig2, use_container_width=True)