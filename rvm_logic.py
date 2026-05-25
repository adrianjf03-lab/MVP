
"""
rvm_logic.py — Radar de Vulnerabilidad Macro (RVM 4.2) para FirstFolio
=======================================================================
Calcula el Índice de Vulnerabilidad (IV Score) para divisas EM y G10
usando tres componentes de riesgo matemáticamente distintos:

  1. Volatilidad Asimétrica (Vol_Asim): Desviación estándar anualizada de los
     retornos logarítmicos en la dirección de depreciación. Captura el riesgo
     específico de cola bajista, ignorando la volatilidad al alza (irrelevante
     para la métrica de estrés).

  2. Volatilidad Total (Vol_Total): Volatilidad histórica anualizada estándar.
     Complementa la Vol_Asim capturando pares donde la turbulencia es simétrica.

  3. Devaluación Anual (%): Variación porcentual del par en los últimos 252 días
     de trading, orientada según la dirección de riesgo del par (directo vs. inverso).

El IV Score final combina estos tres componentes con pesos documentados:
  IV = 0.30·Comp_Asim_Abs + 0.10·Comp_Asim_Rel + 0.10·Comp_Hist + 0.30·Comp_Vol_Total + 0.20·Comp_Deval

Arquitectura:
  - Los datos crudos se descargan con una función de módulo (caché estable con @st.cache_data).
  - RVMAnalytics opera sobre DataFrames puros sin mutar los datos de entrada.
  - La instancia global `analytics` se expone para su uso en app.py.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Tuple

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from datetime import datetime, timedelta
from scipy.stats import linregress

logger = logging.getLogger("firstfolio.rvm")

# ---------------------------------------------------------------------------
# Configuración de activos
# ---------------------------------------------------------------------------

# Convención de dirección:
#   Directo=True  → par cotizado como USD/Moneda Local (ej. MXN=X = 1 USD = N MXN)
#                   Un precio creciente = depreciación de la ML = RIESGO.
#   Directo=False → par cotizado como Moneda/USD (ej. EURUSD=X = 1 EUR = N USD)
#                   Un precio decreciente = depreciación de la ML = RIESGO.

ACTIVOS: dict[str, dict[str, dict]] = {
    "LatAm": {
        "BRL=X": {"Pais": "Brasil",    "ISO": "BRA", "Directo": True},
        "MXN=X": {"Pais": "México",    "ISO": "MEX", "Directo": True},
        "COP=X": {"Pais": "Colombia",  "ISO": "COL", "Directo": True},
        "CLP=X": {"Pais": "Chile",     "ISO": "CHL", "Directo": True},
        "PEN=X": {"Pais": "Perú",      "ISO": "PER", "Directo": True},
    },
    "Asia": {
        "JPY=X": {"Pais": "Japón",    "ISO": "JPN", "Directo": True},
        "CNY=X": {"Pais": "China",    "ISO": "CHN", "Directo": True},
        "INR=X": {"Pais": "India",    "ISO": "IND", "Directo": True},
        "KRW=X": {"Pais": "Corea",    "ISO": "KOR", "Directo": True},
    },
    "G10 (Ref)": {
        "EURUSD=X": {"Pais": "Eurozona",    "ISO": "EMU", "Directo": False},
        "GBPUSD=X": {"Pais": "Reino Unido", "ISO": "GBR", "Directo": False},
    },
}


@dataclass
class UmbralesRVM:
    """
    Umbrales de calibración para la normalización absoluta del IV Score.

    vol_asim_critica:  Nivel de Vol. Asimétrica anualizada (%) considerado crítico.
                       EM currencies históricamente muestran ~8-15% en periodos de estrés.
    deval_critica:     Depreciación anual (%) considerada crítica para un EM.
    vol_total_critica: Volatilidad total anualizada (%) considerada crítica.
    """
    vol_asim_critica: float = 12.0
    deval_critica: float = 20.0
    vol_total_critica: float = 15.0


# ---------------------------------------------------------------------------
# Descarga de datos — función de módulo para caché estable de Streamlit
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600)
def _descargar_datos_rvm() -> pd.DataFrame:
    """
    Descarga y preprocesa los datos históricos de todos los activos del RVM.
    Decorado a nivel de módulo (no en un método) para que @st.cache_data genere
    un hash estable e independiente del estado del objeto.

    Returns:
        DataFrame con métricas intermedias por activo:
        Region, Pais, ISO, Vol_Asim, Vol_Total, Devaluacion, Tendencia, R2, Z_Score_Current.
    """
    fecha_fin = datetime.now()
    fecha_inicio = fecha_fin - timedelta(days=730)  # 2 años de historial
    resultados: list[dict] = []

    for region, tickers in ACTIVOS.items():
        for ticker, info in tickers.items():
            try:
                df = yf.download(
                    ticker,
                    start=fecha_inicio,
                    end=fecha_fin,
                    progress=False,
                    auto_adjust=True,
                )

                if df.empty or len(df) < 252:
                    logger.warning(
                        "Historial insuficiente para %s (%d filas). Omitiendo.",
                        ticker, len(df),
                    )
                    continue

                df = df.dropna(subset=["Close"])
                close = df["Close"].squeeze()  # Garantiza Series 1D

                # ── 1. Retornos Logarítmicos ─────────────────────────────────
                # log(P_t / P_{t-1}): invariante a escala, aditivos en el tiempo.
                log_ret = np.log(close / close.shift(1)).dropna()

                # ── 2. Selección de Retornos en Dirección de Riesgo ──────────
                # Para pares directos (USD/ML): riesgo = depreciación ML = precio sube → ret > 0.
                # Para pares inversos (ML/USD): riesgo = depreciación ML = precio cae → ret < 0.
                if info["Directo"]:
                    retornos_riesgo = log_ret[log_ret > 0]
                    # Devaluación: cuánto sube el par (más caro el dólar) en 252 días
                    precio_base = float(close.iloc[-252])
                    precio_actual = float(close.iloc[-1])
                    devaluacion = ((precio_actual - precio_base) / precio_base) * 100
                else:
                    retornos_riesgo = log_ret[log_ret < 0]
                    # Devaluación: cuánto cae el par (vale menos la divisa G10 vs USD)
                    precio_base = float(close.iloc[-252])
                    precio_actual = float(close.iloc[-1])
                    devaluacion = ((precio_base - precio_actual) / precio_base) * 100

                # ── 3. Volatilidades (Anualizadas) ────────────────────────────
                # Vol_Asim: semi-desviación en la dirección de riesgo. Factor √252 anualiza.
                vol_asim = (
                    float(retornos_riesgo.std() * np.sqrt(252) * 100)
                    if len(retornos_riesgo) > 1
                    else 0.0
                )
                vol_total = float(log_ret.std() * np.sqrt(252) * 100)

                # ── 4. Tendencia Reciente (Regresión lineal sobre 30 días) ────
                reciente = close.tail(30).values.flatten()
                x = np.arange(len(reciente), dtype=float)
                slope, _, r_value, _, _ = linregress(x, reciente)

                # Ajuste de dirección: para pares directos, pendiente positiva = riesgo.
                # Para pares inversos, pendiente negativa = riesgo (moneda se deprecia).
                slope_riesgo = slope if info["Directo"] else -slope
                tendencia = "↗️ Acelerando" if slope_riesgo > 0 else "↘️ Relajando"
                r_squared = float(r_value ** 2)

                # ── 5. Z-Score Histórico (Volatilidad Actual vs. Distribución Histórica) ─
                # CORRECCIÓN MATEMÁTICA: Se compara la ÚLTIMA ventana rolling de 30 días
                # (volatilidad más reciente) contra la distribución histórica de TODAS
                # las ventanas rolling de 30 días. Responde: "¿Es la vol. actual inusual?"
                rolling_vol = log_ret.rolling(window=30).std() * np.sqrt(252) * 100
                rolling_vol_clean = rolling_vol.dropna()

                if len(rolling_vol_clean) > 1 and rolling_vol_clean.std() > 0:
                    vol_actual_30d = float(rolling_vol_clean.iloc[-1])
                    z_score = float(
                        (vol_actual_30d - rolling_vol_clean.mean())
                        / rolling_vol_clean.std()
                    )
                else:
                    z_score = 0.0

                resultados.append({
                    "Region": region,
                    "Pais": info["Pais"],
                    "ISO": info["ISO"],
                    "Vol_Asim": vol_asim,
                    "Vol_Total": vol_total,
                    "Devaluacion": devaluacion,
                    "Tendencia": tendencia,
                    "R2": r_squared,
                    "Z_Score_Current": z_score,
                })

            except Exception as e:
                logger.error("Error procesando ticker '%s': %s", ticker, e)
                continue

    return pd.DataFrame(resultados)


# ---------------------------------------------------------------------------
# Motor de análisis RVM
# ---------------------------------------------------------------------------

class RVMAnalytics:
    """
    Motor del Radar de Vulnerabilidad Macro (RVM 4.2).

    Responsabilidades:
      - Obtener datos (delegando a la función de caché del módulo).
      - Calcular el IV Score sobre una copia del DataFrame.
      - Generar visualizaciones con Plotly.
    """

    def __init__(self, umbrales: UmbralesRVM | None = None) -> None:
        self.umbrales = umbrales or UmbralesRVM()

    def obtener_datos(self) -> pd.DataFrame:
        """Delega la descarga a la función de módulo cacheada."""
        return _descargar_datos_rvm()

    def calcular_iv_score(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calcula el IV Score sobre una COPIA del DataFrame (no muta el original).

        Fórmula descompuesta con pesos explícitos (suman 1.0):
          ┌─────────────────────────────────────────────────────────────────────┐
          │ Componente             │ Peso │ Descripción                        │
          ├─────────────────────────────────────────────────────────────────────┤
          │ Comp_Asim_Abs          │ 0.30 │ Vol_Asim normalizada por umbral     │
          │ Comp_Asim_Rel          │ 0.10 │ Ranking percentil de Vol_Asim       │
          │ Comp_Hist_Z            │ 0.10 │ Sigmoide del Z-Score (vol actual)   │
          │ Comp_Vol_Total         │ 0.30 │ Vol_Total normalizada por umbral     │
          │ Comp_Deval             │ 0.20 │ Devaluación normalizada por umbral  │
          └─────────────────────────────────────────────────────────────────────┘

        Args:
            df: DataFrame con columnas Vol_Asim, Vol_Total, Devaluacion, Z_Score_Current.

        Returns:
            Nuevo DataFrame con columnas IV_Score y Senal añadidas.
        """
        result = df.copy()

        # ── Componente 1: Volatilidad Asimétrica Absoluta ─────────────────────
        # Qué fracción del umbral crítico representa la vol. asimétrica del país.
        comp_asim_abs = (result["Vol_Asim"] / self.umbrales.vol_asim_critica).clip(0, 1) * 100

        # ── Componente 2: Volatilidad Asimétrica Relativa ─────────────────────
        # Ranking percentil dentro del universo — captura quién es más volátil hoy.
        comp_asim_rel = result["Vol_Asim"].rank(pct=True) * 100

        # ── Componente 3: Histórico — Anormalidad del Nivel Actual ──────────
        # Sigmoid del Z-Score: convierte desviaciones estándar a [0, 100].
        # Z > 0 → vol actual por encima de su media histórica → mayor riesgo.
        comp_hist_z = (1 / (1 + np.exp(-result["Z_Score_Current"]))) * 100

        # ── Componente 4: Volatilidad Total Normalizada ───────────────────────
        comp_vol_total = (result["Vol_Total"] / self.umbrales.vol_total_critica).clip(0, 1) * 100

        # ── Componente 5: Devaluación Anual Normalizada ───────────────────────
        # clip(lower=0): solo la depreciación suma riesgo (apreciaciones no restan).
        comp_deval = (
            result["Devaluacion"].clip(lower=0) / self.umbrales.deval_critica
        ).clip(0, 1) * 100

        # ── IV Score Final (pesos documentados arriba, suman 1.0) ─────────────
        result["IV_Score"] = (
            0.30 * comp_asim_abs
            + 0.10 * comp_asim_rel
            + 0.10 * comp_hist_z
            + 0.30 * comp_vol_total
            + 0.20 * comp_deval
        ).round(1)

        # ── Señal semafórica ───────────────────────────────────────────────────
        result["Senal"] = np.select(
            condlist=[result["IV_Score"] > 60, result["IV_Score"] > 40],
            choicelist=["🔴 CRÍTICO", "⚠️ ALERTA"],
            default="🟢 ESTABLE",
        )

        return result

    def generar_graficos(
        self, df: pd.DataFrame
    ) -> Tuple[go.Figure, go.Figure]:
        """
        Genera el mapa choropleth de calor y el radar de riesgo regional.

        Args:
            df: DataFrame con IV_Score ya calculado.

        Returns:
            Tupla (fig_map, fig_radar).
        """
        base_layout = dict(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e0e0e0", family="monospace"),
        )

        # ── Mapa de Calor Choropleth ───────────────────────────────────────────
        fig_map = px.choropleth(
            df,
            locations="ISO",
            color="IV_Score",
            color_continuous_scale="RdYlGn_r",
            range_color=[0, 100],
            hover_name="Pais",
            hover_data={
                "IV_Score": True,
                "Senal": True,
                "Vol_Asim": ":.1f",
                "Devaluacion": ":.1f",
                "Tendencia": True,
            },
            title="<b>MAPA DE VULNERABILIDAD ESTRUCTURAL (IV Score)</b>",
            locationmode="ISO-3",
        )
        fig_map.update_layout(
            margin=dict(l=0, r=0, t=40, b=0),
            geo=dict(
                bgcolor="rgba(0,0,0,0)",
                showland=True,
                landcolor="#1a1f2e",
                showocean=True,
                oceancolor="#0e1117",
                showframe=False,
                coastlinecolor="#30363d",
            ),
            coloraxis_colorbar=dict(
                title="IV Score",
                tickvals=[0, 25, 50, 75, 100],
                ticktext=["0 Estable", "25", "50 Alerta", "75", "100 Crítico"],
            ),
            **base_layout,
        )

        # ── Radar Regional ─────────────────────────────────────────────────────
        COLORES_REGION = {
            "LatAm": "#FF5733",
            "Asia": "#33C1FF",
            "G10 (Ref)": "#AAAAAA",
        }

        fig_radar = go.Figure()

        for region in df["Region"].unique():
            df_reg = df[df["Region"] == region].sort_values("Pais")
            paises = df_reg["Pais"].tolist()
            scores = df_reg["IV_Score"].tolist()

            # Cierre del polígono: repetir primer punto sobre datos ORDENADOS
            r_vals = scores + [scores[0]]
            theta_vals = paises + [paises[0]]

            fig_radar.add_trace(
                go.Scatterpolar(
                    r=r_vals,
                    theta=theta_vals,
                    fill="toself",
                    fillcolor=COLORES_REGION.get(region, "#FFFFFF") + "33",  # 20% opacidad
                    name=region,
                    line=dict(color=COLORES_REGION.get(region, "white"), width=2),
                    hovertemplate="<b>%{theta}</b><br>IV Score: %{r:.1f}<extra></extra>",
                )
            )

        fig_radar.update_layout(
            polar=dict(
                bgcolor="#111827",
                radialaxis=dict(
                    range=[0, 100],
                    tickvals=[25, 50, 75, 100],
                    ticktext=["25", "50", "75", "100"],
                    gridcolor="#30363d",
                    linecolor="#30363d",
                ),
                angularaxis=dict(gridcolor="#30363d", linecolor="#30363d"),
            ),
            title="<b>RADAR REGIONAL</b>",
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=-0.15,
                xanchor="center",
                x=0.5,
            ),
            **base_layout,
        )

        return fig_map, fig_radar


# ---------------------------------------------------------------------------
# Instancia global — punto de acceso para app.py
# ---------------------------------------------------------------------------
# Nota: Se usa "analytics" (corrección del typo original "analitics").
analytics = RVMAnalytics()
