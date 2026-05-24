
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from scipy.stats import linregress
from typing import Tuple

# --- CONFIGURACIÓN ESTRUCTURAL ---
ACTIVOS = {
    'LatAm': {
        'BRL=X': {'Pais': 'Brasil', 'ISO': 'BRA', 'Directo': True},
        'MXN=X': {'Pais': 'México', 'ISO': 'MEX', 'Directo': True},
        'COP=X': {'Pais': 'Colombia', 'ISO': 'COL', 'Directo': True},
        'CLP=X': {'Pais': 'Chile', 'ISO': 'CHL', 'Directo': True},
        'PEN=X': {'Pais': 'Perú', 'ISO': 'PER', 'Directo': True}
    },
    'Asia': {
        'JPY=X': {'Pais': 'Japón', 'ISO': 'JPN', 'Directo': True},
        'CNY=X': {'Pais': 'China', 'ISO': 'CHN', 'Directo': True},
        'INR=X': {'Pais': 'India', 'ISO': 'IND', 'Directo': True},
        'KRW=X': {'Pais': 'Corea', 'ISO': 'KOR', 'Directo': True}
    },
    'G10 (Ref)': {
        'EURUSD=X': {'Pais': 'Eurozona', 'ISO': 'EUR', 'Directo': False},
        'GBPUSD=X': {'Pais': 'Reino Unido', 'ISO': 'GBR', 'Directo': False}
    }
}

class RVMAnalytics:
    def __init__(self):
        self.umbrales = {'vol_asim_critica': 12.0, 'deval_critica': 20.0}

    @st.cache_data(ttl=3600, show_spinner=False)
    def obtener_datos(_self) -> pd.DataFrame:
        """Descarga e infiere métricas usando YF.download en Batch para máxima velocidad."""
        fecha_fin = datetime.now()
        fecha_inicio = fecha_fin - timedelta(days=730)
        
        todos_los_tickers = [ticker for region in ACTIVOS.values() for ticker in region.keys()]
        
        try:
            df_crudo = yf.download(todos_los_tickers, start=fecha_inicio, end=fecha_fin, progress=False)
            df_cierres = df_crudo['Close'].dropna(how='all') 
        except Exception as e:
            st.error(f"Error crítico al obtener datos de Yahoo Finance: {e}")
            return pd.DataFrame()

        resultados = []
        
        for region, tickers_info in ACTIVOS.items():
            for ticker, info in tickers_info.items():
                if ticker not in df_cierres.columns:
                    continue
                
                serie_precio = df_cierres[ticker].dropna()
                if len(serie_precio) < 200: 
                    continue

                log_ret = np.log(serie_precio / serie_precio.shift(1)).dropna()
                
                if info['Directo']:
                    retornos_malos = log_ret[log_ret > 0]
                    devaluacion = ((serie_precio.iloc[-1] - serie_precio.iloc[-252]) / serie_precio.iloc[-252]) * 100
                    slope_factor = 1 
                else:
                    retornos_malos = log_ret[log_ret < 0]
                    devaluacion = ((serie_precio.iloc[-252] - serie_precio.iloc[-1]) / serie_precio.iloc[-252]) * 100
                    slope_factor = -1 

                vol_asim = retornos_malos.std(ddof=1) * np.sqrt(252) * 100 if len(retornos_malos) > 1 else 0
                vol_total = log_ret.std(ddof=1) * np.sqrt(252) * 100
                
                reciente = serie_precio.tail(30).values
                slope, _, r_value, _, _ = linregress(np.arange(len(reciente)), reciente)
                
                slope_ajustada = slope * slope_factor
                tendencia = "↗️ Acelerando" if slope_ajustada > 0 else "↘️ Relajando"
                
                hist_vol = log_ret.rolling(30).std(ddof=1) * np.sqrt(252) * 100
                std_historica = hist_vol.std(ddof=1)
                z_score = (vol_total - hist_vol.mean()) / std_historica if std_historica > 0.001 else 0.0

                resultados.append({
                    'Region': region, 'Pais': info['Pais'], 'ISO': info['ISO'],
                    'Vol_Asim': vol_asim, 'Vol_Total': vol_total,
                    'Devaluacion': devaluacion, 'Tendencia': tendencia,
                    'R2': r_value**2, 'Z_Score': z_score
                })

        return pd.DataFrame(resultados)

    def calcular_iv_score(self, df: pd.DataFrame) -> pd.DataFrame:
        """Cálculo Cuantitativo Vectorizado del Índice de Vulnerabilidad."""
        if df.empty: return df

        abs_asim = (df['Vol_Asim'] / self.umbrales['vol_asim_critica']).clip(0, 1) * 100
        abs_deval = (df['Devaluacion'].clip(lower=0) / self.umbrales['deval_critica']).clip(0, 1) * 100
        rel_asim = df['Vol_Asim'].rank(pct=True) * 100
        
        hist_score = (1 / (1 + np.exp(-df['Z_Score'].fillna(0)))) * 100
        
        score_asim_final = (0.6 * abs_asim) + (0.2 * rel_asim) + (0.2 * hist_score)
        
        df['IV_Score'] = (0.5 * score_asim_final) + \
                         (0.3 * (df['Vol_Total'] / 15).clip(0, 1) * 100) + \
                         (0.2 * abs_deval)
                         
        df['IV_Score'] = df['IV_Score'].fillna(0).round(1)
        
        conditions = [df['IV_Score'] > 60, df['IV_Score'] > 40]
        df['Senal'] = np.select(conditions, ['🔴 CRÍTICO', '⚠️ ALERTA'], default='🟢 ESTABLE')
        
        return df

    def generar_graficos(self, df: pd.DataFrame) -> Tuple[go.Figure, go.Figure]:
        """Devuelve Mapas y Radiales Plotly con semántica visual y transparencias."""
        layout = dict(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color='white'))
        
        # Mapa con escala semántica (Verde -> Amarillo -> Rojo)
        fig_map = px.choropleth(
            df, locations="ISO", color="IV_Score",
            color_continuous_scale=[(0, "#2ea043"), (0.5, "#d29922"), (1, "#f85149")], 
            range_color=[0, 100],
            hover_name="Pais", 
            hover_data={'ISO': False, 'IV_Score': ':.1f', 'Senal': True},
            title="<b>Mapa Global de Estrés Estructural</b><br><sup>Tonos cálidos indican alta vulnerabilidad asimétrica</sup>"
        )
        fig_map.update_layout(
            margin=dict(l=0, r=0, t=50, b=0), 
            geo=dict(bgcolor='rgba(0,0,0,0)', showland=True, landcolor='#222'), 
            **layout
        )

        # Radar Chart con transparencias (Hex '40')
        fig_radar = go.Figure()
        colores = {'LatAm': '#FF5733', 'Asia': '#33C1FF', 'G10 (Ref)': '#AAAAAA'}
        
        for reg in df['Region'].unique():
            dfr = df[df['Region'] == reg]
            r = list(dfr['IV_Score']) + [dfr['IV_Score'].iloc[0]]
            t = list(dfr['Pais']) + [dfr['Pais'].iloc[0]]
            
            color_base = colores.get(reg, '#ffffff')
            fig_radar.add_trace(go.Scatterpolar(
                r=r, theta=t, fill='toself', name=reg, 
                fillcolor=color_base + '40', 
                line=dict(color=color_base, width=2),
                hoverinfo="r+theta+name"
            ))
            
        fig_radar.update_layout(polar=dict(bgcolor="#111", radialaxis=dict(range=[0, 100])), **layout)

        return fig_map, fig_radar
