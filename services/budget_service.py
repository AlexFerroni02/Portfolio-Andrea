import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from typing import Dict, Tuple

def get_monthly_summary(selected_month: str, df_budget: pd.DataFrame, df_trans: pd.DataFrame) -> Dict[str, float]:
    """
    Calcola un riepilogo finanziario per il mese selezionato.
    """
    df_month = df_budget[df_budget['date'].dt.strftime('%Y-%m') == selected_month]

    entrate = df_month[df_month['type'] == 'Entrata']['amount'].sum()
    uscite = df_month[df_month['type'] == 'Uscita']['amount'].sum()
    risparmio = entrate - uscite
    savings_rate = (risparmio / entrate * 100) if entrate > 0 else 0

    investito_mese = 0.0
    if not df_trans.empty:
        mask_inv = df_trans['date'].dt.strftime('%Y-%m') == selected_month
        investito_mese = -df_trans[mask_inv]['local_value'].sum()

    return {
        "entrate": entrate,
        "uscite": uscite,
        "risparmio": risparmio,
        "savings_rate": savings_rate,
        "investito_mese": investito_mese
    }

def calculate_net_worth_trend(df_chart: pd.DataFrame) -> Tuple[pd.DataFrame, LinearRegression]:
    """
    Calcola la linea di trend per il grafico del patrimonio netto.
    """
    if len(df_chart) < 2:
        return pd.DataFrame(), None

    X = np.array([(d - df_chart['date'].min()).days for d in df_chart['date']]).reshape(-1, 1)
    y = df_chart['net_worth'].values
    model = LinearRegression().fit(X, y)
    
    trend_dates = pd.date_range(start=df_chart['date'].min(), end=df_chart['date'].max() + pd.DateOffset(months=6))
    trend_X = np.array([(d - df_chart['date'].min()).days for d in trend_dates]).reshape(-1, 1)
    trend_y = model.predict(trend_X)
    
    df_trend = pd.DataFrame({'date': trend_dates, 'trend': trend_y})
    return df_trend, model

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