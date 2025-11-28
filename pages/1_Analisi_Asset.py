import streamlit as st
import pandas as pd
import plotly.express as px
from utils import load_and_clean_data

st.set_page_config(page_title="Analisi Asset", layout="wide", page_icon="🔎")
st.title("🔎 Dettaglio ETF")

df_trans, df_map, df_prices, df_full = load_and_clean_data()

if df_full is None:
    st.stop()

products = df_full['product'].unique()
selected_product = st.selectbox("Seleziona:", products)

df_asset = df_full[df_full['product'] == selected_product]
ticker = df_asset['ticker'].iloc[0] if not df_asset.empty else None

if ticker:
    st.info(f"Ticker associato: **{ticker}**")
    # Qui puoi aggiungere grafici specifici come visto prima
    st.dataframe(df_asset)
else:
    st.warning("Questo asset non ha ancora un ticker associato.")