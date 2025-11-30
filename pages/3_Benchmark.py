import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from utils import get_data, make_sidebar, style_chart_for_mobile

st.set_page_config(page_title="Benchmark", layout="wide", page_icon="⚖️")
make_sidebar()
st.title("⚖️ Sfida il Mercato")

# --- FUNZIONE DI CALCOLO CON CACHE DEDICATA ---
@st.cache_data
def run_benchmark_simulation(bench_ticker, df_trans, df_map, df_prices):
    # ... (Il resto della funzione cachata rimane invariato)
    df_trans['date'] = pd.to_datetime(df_trans['date'], errors='coerce').dt.normalize()
    if not df_prices.empty:
        df_prices['date'] = pd.to_datetime(df_prices['date'], errors='coerce').dt.normalize()
    
    df_full = df_trans.merge(df_map, on='isin', how='left')
    start_date = df_trans['date'].min()
    end_date = df_prices['date'].max() if not df_prices.empty else df_trans['date'].max()

    try:
        bench_hist = yf.download(bench_ticker, start=start_date, end=end_date, progress=False)
        if bench_hist.empty:
            raise ValueError(f"Nessun dato trovato per '{bench_ticker}'.")
        
        bench_hist = bench_hist[['Close']].iloc[:, 0]
        bench_hist.index = pd.to_datetime(bench_hist.index).normalize()
        full_idx = pd.date_range(start=bench_hist.index.min(), end=bench_hist.index.max(), freq='D')
        bench_hist = bench_hist.reindex(full_idx).ffill()
    except Exception as e:
        st.error(f"Errore download benchmark: {e}")
        return None

    timeline = pd.date_range(start=start_date, end=end_date, freq='D').normalize()
    my_val_history, bench_val_history = [], []
    pivot_user = pd.DataFrame()
    if not df_prices.empty:
        pivot_user = df_prices.pivot_table(index='date', columns='ticker', values='close_price', aggfunc='last').sort_index().ffill()
    
    trans_grouped = df_full.groupby('date')
    user_qty, bench_qty, tot_invested_bench = {}, 0, 0.0

    for d in timeline:
        daily_cash = 0
        if d in trans_grouped.groups:
            moves = trans_grouped.get_group(d)
            for _, row in moves.iterrows():
                tk = row['ticker']
                if pd.notna(tk): user_qty[tk] = user_qty.get(tk, 0) + row['quantity']
                cash = -row['local_value']
                daily_cash += cash
        if daily_cash != 0:
            try:
                idx = bench_hist.index.asof(d)
                if pd.notna(idx):
                    p_bench = bench_hist.at[idx]
                    if pd.notna(p_bench) and p_bench > 0:
                        bench_qty += daily_cash / p_bench
                        tot_invested_bench += daily_cash
            except: pass
        val_user = 0
        for tk, q in user_qty.items():
            if q > 0.001 and tk in pivot_user.columns:
                try:
                    idx = pivot_user.index.asof(d)
                    if pd.notna(idx):
                        p = pivot_user.at[idx, tk]
                        if pd.notna(p): val_user += q * p
                except: pass
        val_bench = 0
        try:
            idx = bench_hist.index.asof(d)
            if pd.notna(idx):
                p_bench = bench_hist.at[idx]
                if pd.notna(p_bench): val_bench = bench_qty * p_bench
        except: pass
        my_val_history.append(val_user)
        bench_val_history.append(val_bench)

    df_chart = pd.DataFrame({'Data': timeline, 'Tu': my_val_history, 'Benchmark': bench_val_history})
    df_chart = df_chart[(df_chart['Tu'] > 0) | (df_chart['Benchmark'] > 0)]
    return df_chart, tot_invested_bench

# --- INTERFACCIA UTENTE ---
df_trans, df_map, df_prices = get_data("transactions"), get_data("mapping"), get_data("prices")

if df_trans.empty:
    st.warning("⚠️ Carica prima i dati nella pagina Gestione."), st.stop()

col1, col2 = st.columns([1, 3])
bench_ticker = col1.text_input("Ticker Yahoo", value="SWDA.MI")
col2.info("Simulazione Shadow: Ogni euro investito nel tuo portafoglio viene replicato virtualmente sul Benchmark nello stesso istante.")

if bench_ticker:
    with st.spinner(f"Calcolo simulazione su {bench_ticker}..."):
        results = run_benchmark_simulation(bench_ticker, df_trans, df_map, df_prices)

    if results:
        df_chart, tot_invested_bench = results
        final_user, final_bench = df_chart['Tu'].iloc[-1], df_chart['Benchmark'].iloc[-1]
        diff = final_user - final_bench
        st.divider()
        k1, k2, k3 = st.columns(3)
        k1.metric("Il Tuo Portafoglio", f"€ {final_user:,.2f}")
        k2.metric(f"Benchmark ({bench_ticker})", f"€ {final_bench:,.2f}")
        k3.metric("Alpha (Differenza)", f"€ {diff:,.2f}", delta=f"{((final_user - final_bench)/final_bench)*100:.2f}%" if final_bench else "0%")

        st.subheader("📈 Gara di Rendimento")
        fig1 = go.Figure()
        fig1.add_trace(go.Scatter(x=df_chart['Data'], y=df_chart['Tu'], name='Il Tuo Portafoglio', line=dict(color='#00CC96', width=3)))
        fig1.add_trace(go.Scatter(x=df_chart['Data'], y=df_chart['Benchmark'], name=f'Benchmark ({bench_ticker})', line=dict(color='#A0A0A0', width=2, dash='dot')))
        fig1.update_layout(title_text="Valore nel Tempo (€)")
        fig1 = style_chart_for_mobile(fig1) # APPLICA STILE
        st.plotly_chart(fig1, use_container_width=True)

        st.subheader("🌊 Analisi del Rischio (Drawdown)")
        st.caption("Quanto perdi dai massimi? L'area rossa indica i tuoi crolli.")
        df_chart['Tu_Max'] = df_chart['Tu'].cummax()
        df_chart['Bench_Max'] = df_chart['Benchmark'].cummax()
        df_chart['Tu_DD'] = 0.0
        mask_tu = df_chart['Tu_Max'] > 0
        df_chart.loc[mask_tu, 'Tu_DD'] = ((df_chart.loc[mask_tu, 'Tu'] - df_chart.loc[mask_tu, 'Tu_Max']) / df_chart.loc[mask_tu, 'Tu_Max']) * 100
        df_chart['Bench_DD'] = 0.0
        mask_bench = df_chart['Bench_Max'] > 0
        df_chart.loc[mask_bench, 'Bench_DD'] = ((df_chart.loc[mask_bench, 'Benchmark'] - df_chart.loc[mask_bench, 'Bench_Max']) / df_chart.loc[mask_bench, 'Bench_Max']) * 100
        
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=df_chart['Data'], y=df_chart['Tu_DD'], name='Il Tuo Drawdown', fill='tozeroy', line=dict(color='#EF553B', width=1)))
        fig2.add_trace(go.Scatter(x=df_chart['Data'], y=df_chart['Bench_DD'], name='Benchmark', line=dict(color='#A0A0A0', width=1, dash='dot')))
        fig2.update_layout(title_text="Perdita dai Massimi (%)", yaxis_ticksuffix="%")
        fig2 = style_chart_for_mobile(fig2) # APPLICA STILE
        st.plotly_chart(fig2, use_container_width=True)