"""
rvm_logic.py - Radar de Vulnerabilidad Macro (RVM 4.2) para FirstFolio
=======================================================================

Calcula un Indice de Vulnerabilidad (IV Score) para divisas EM y G10 usando
riesgo de depreciacion orientado por la convencion del par:

  - Directo=True:  USD/Moneda Local. Si el precio sube, la moneda local se
    deprecia frente al USD.
  - Directo=False: Moneda Local/USD. Si el precio baja, la moneda local se
    deprecia frente al USD.

La metrica central es una semi-volatilidad de downside:
  risk_return = log_return ajustado para que valores positivos representen
  depreciacion de la moneda local.

  Vol_Asim = sqrt(mean(max(risk_return, 0)^2)) * sqrt(252) * 100

Esta definicion evita el sesgo de calcular la desviacion estandar solo sobre
observaciones adversas, que puede subestimar el riesgo al ignorar la frecuencia
de los eventos negativos.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from scipy.stats import linregress


logger = logging.getLogger("firstfolio.rvm")

TRADING_DAYS = 252
ROLLING_WINDOW = 30


@dataclass(frozen=True)
class ActivoRVM:
    pais: str
    iso: str
    directo: bool


@dataclass(frozen=True)
class UmbralesRVM:
    """Umbrales absolutos usados para normalizar componentes a escala 0-100."""

    vol_asim_critica: float = 12.0
    deval_critica: float = 20.0
    vol_total_critica: float = 15.0


@dataclass(frozen=True)
class PesosRVM:
    """Pesos del IV Score. Deben sumar 1.0."""

    asim_abs: float = 0.30
    asim_rel: float = 0.10
    hist_z: float = 0.10
    vol_total: float = 0.30
    deval: float = 0.20

    @property
    def total(self) -> float:
        return self.asim_abs + self.asim_rel + self.hist_z + self.vol_total + self.deval


ACTIVOS: dict[str, dict[str, ActivoRVM]] = {
    "LatAm": {
        "BRL=X": ActivoRVM("Brasil", "BRA", True),
        "MXN=X": ActivoRVM("México", "MEX", True),
        "COP=X": ActivoRVM("Colombia", "COL", True),
        "CLP=X": ActivoRVM("Chile", "CHL", True),
        "PEN=X": ActivoRVM("Perú", "PER", True),
    },
    "Asia": {
        "JPY=X": ActivoRVM("Japón", "JPN", True),
        "CNY=X": ActivoRVM("China", "CHN", True),
        "INR=X": ActivoRVM("India", "IND", True),
        "KRW=X": ActivoRVM("Corea del Sur", "KOR", True),
    },
    "G10 (Ref)": {
        # DEU se usa como proxy visual del EUR en el choropleth porque EMU no es ISO-3.
        "EURUSD=X": ActivoRVM("Eurozona (EUR)", "DEU", False),
        "GBPUSD=X": ActivoRVM("Reino Unido", "GBR", False),
    },
}


COLORES_REGION = {
    "LatAm": "#FF5733",
    "Asia": "#33C1FF",
    "G10 (Ref)": "#AAAAAA",
}


def _extraer_close(df: pd.DataFrame) -> pd.Series:
    """Extrae una serie Close robusta ante columnas simples o MultiIndex."""
    if df.empty:
        return pd.Series(dtype=float)

    if isinstance(df.columns, pd.MultiIndex):
        if "Close" not in df.columns.get_level_values(0):
            return pd.Series(dtype=float)
        close = df["Close"]
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
    else:
        if "Close" not in df.columns:
            return pd.Series(dtype=float)
        close = df["Close"]

    return pd.to_numeric(close, errors="coerce").dropna().astype(float)


def _downside_vol_anualizada(risk_returns: pd.Series) -> float:
    """Semi-volatilidad anualizada con umbral cero."""
    if risk_returns.empty:
        return 0.0
    adverse = risk_returns.clip(lower=0)
    return float(np.sqrt(np.mean(np.square(adverse))) * np.sqrt(TRADING_DAYS) * 100)


def _downside_vol_array(values: np.ndarray) -> float:
    adverse = np.clip(values, 0, None)
    return float(np.sqrt(np.mean(np.square(adverse))) * np.sqrt(TRADING_DAYS) * 100)


def _calcular_devaluacion(close: pd.Series, directo: bool) -> float:
    precio_base = float(close.iloc[-TRADING_DAYS])
    precio_actual = float(close.iloc[-1])
    if precio_base <= 0 or precio_actual <= 0:
        return 0.0

    if directo:
        return ((precio_actual - precio_base) / precio_base) * 100
    return ((precio_base - precio_actual) / precio_base) * 100


def _calcular_tendencia(close: pd.Series, directo: bool) -> tuple[str, float]:
    reciente = np.log(close.tail(ROLLING_WINDOW).to_numpy(dtype=float))
    x = np.arange(len(reciente), dtype=float)
    slope, _, r_value, _, _ = linregress(x, reciente)

    slope_riesgo = slope if directo else -slope
    tendencia = "↗ Acelerando" if slope_riesgo > 0 else "↘ Relajando"
    return tendencia, float(r_value**2)


def _calcular_zscore_actual(risk_returns: pd.Series) -> float:
    rolling_downside = risk_returns.rolling(ROLLING_WINDOW).apply(
        _downside_vol_array,
        raw=True,
    )
    rolling_clean = rolling_downside.dropna()
    if len(rolling_clean) <= 1:
        return 0.0

    std = float(rolling_clean.std())
    if std <= 1e-12:
        return 0.0

    return float((rolling_clean.iloc[-1] - rolling_clean.mean()) / std)


@st.cache_data(ttl=3600, show_spinner=False)
def _descargar_datos_rvm() -> pd.DataFrame:
    """
    Descarga y preprocesa historicos de todos los activos del RVM.

    Returns:
        DataFrame con una fila por activo y metricas intermedias.
    """
    fecha_fin = datetime.now()
    fecha_inicio = fecha_fin - timedelta(days=730)
    resultados: list[dict[str, Any]] = []

    for region, tickers in ACTIVOS.items():
        for ticker, info in tickers.items():
            try:
                df = yf.download(
                    ticker,
                    start=fecha_inicio,
                    end=fecha_fin,
                    progress=False,
                    auto_adjust=True,
                    threads=False,
                )
                close = _extraer_close(df)
                if len(close) < TRADING_DAYS + ROLLING_WINDOW:
                    logger.warning(
                        "Historial insuficiente para %s (%d observaciones).",
                        ticker,
                        len(close),
                    )
                    continue

                log_ret = np.log(close / close.shift(1)).dropna()
                risk_ret = log_ret if info.directo else -log_ret

                vol_asim = _downside_vol_anualizada(risk_ret)
                vol_total = float(risk_ret.std() * np.sqrt(TRADING_DAYS) * 100)
                devaluacion = _calcular_devaluacion(close, info.directo)
                tendencia, r_squared = _calcular_tendencia(close, info.directo)
                z_score = _calcular_zscore_actual(risk_ret)

                resultados.append(
                    {
                        "Ticker": ticker,
                        "Region": region,
                        "Pais": info.pais,
                        "ISO": info.iso,
                        "Directo": info.directo,
                        "Vol_Asim": vol_asim,
                        "Vol_Total": vol_total,
                        "Devaluacion": devaluacion,
                        "Tendencia": tendencia,
                        "R2": r_squared,
                        "Z_Score_Current": z_score,
                    }
                )
            except Exception as exc:
                logger.error("Error procesando ticker %s: %s", ticker, exc)

    return pd.DataFrame(resultados)


def limpiar_cache() -> None:
    """Limpia la cache de descarga RVM."""
    _descargar_datos_rvm.clear()


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    hex_color = hex_color.lstrip("#")
    r, g, b = tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


class RVMAnalytics:
    """Motor del Radar de Vulnerabilidad Macro."""

    def __init__(
        self,
        umbrales: UmbralesRVM | None = None,
        pesos: PesosRVM | None = None,
    ) -> None:
        self.umbrales = umbrales or UmbralesRVM()
        self.pesos = pesos or PesosRVM()
        if not np.isclose(self.pesos.total, 1.0):
            raise ValueError("Los pesos del RVM deben sumar 1.0.")

    def obtener_datos(self) -> pd.DataFrame:
        """Obtiene datos cacheados del RVM."""
        return _descargar_datos_rvm()

    def calcular_iv_score(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calcula el IV Score sobre una copia del DataFrame.

        Componentes:
          - Comp_Asim_Abs: Vol_Asim normalizada contra umbral critico.
          - Comp_Asim_Rel: ranking percentil de Vol_Asim en el universo.
          - Comp_Hist_Z: sigmoide del Z-Score de downside volatility actual.
          - Comp_Vol_Total: volatilidad total normalizada.
          - Comp_Deval: devaluacion anual normalizada.
        """
        if df.empty:
            return df.copy()

        required = {"Vol_Asim", "Vol_Total", "Devaluacion", "Z_Score_Current"}
        missing = required.difference(df.columns)
        if missing:
            raise ValueError(f"Faltan columnas requeridas para IV Score: {sorted(missing)}")

        result = df.copy()
        for col in required:
            result[col] = pd.to_numeric(result[col], errors="coerce").fillna(0.0)

        comp_asim_abs = (
            result["Vol_Asim"] / self.umbrales.vol_asim_critica
        ).clip(0, 1) * 100
        comp_asim_rel = result["Vol_Asim"].rank(pct=True, method="average").fillna(0) * 100
        comp_hist_z = (1 / (1 + np.exp(-result["Z_Score_Current"].clip(-8, 8)))) * 100
        comp_vol_total = (
            result["Vol_Total"] / self.umbrales.vol_total_critica
        ).clip(0, 1) * 100
        comp_deval = (
            result["Devaluacion"].clip(lower=0) / self.umbrales.deval_critica
        ).clip(0, 1) * 100

        result["Comp_Asim_Abs"] = comp_asim_abs.round(1)
        result["Comp_Asim_Rel"] = comp_asim_rel.round(1)
        result["Comp_Hist_Z"] = comp_hist_z.round(1)
        result["Comp_Vol_Total"] = comp_vol_total.round(1)
        result["Comp_Deval"] = comp_deval.round(1)

        result["IV_Score"] = (
            self.pesos.asim_abs * comp_asim_abs
            + self.pesos.asim_rel * comp_asim_rel
            + self.pesos.hist_z * comp_hist_z
            + self.pesos.vol_total * comp_vol_total
            + self.pesos.deval * comp_deval
        ).round(1)

        result["Senal"] = np.select(
            condlist=[result["IV_Score"] >= 60, result["IV_Score"] >= 40],
            choicelist=["🔴 CRÍTICO", "⚠️ ALERTA"],
            default="🟢 ESTABLE",
        )
        return result.sort_values("IV_Score", ascending=False).reset_index(drop=True)

    def generar_graficos(self, df: pd.DataFrame) -> tuple[go.Figure, go.Figure]:
        """Genera el choropleth y el radar regional."""
        if df.empty:
            return go.Figure(), go.Figure()

        base_layout = dict(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e0e0e0"),
        )

        fig_map = px.choropleth(
            df,
            locations="ISO",
            color="IV_Score",
            color_continuous_scale="RdYlGn_r",
            range_color=[0, 100],
            hover_name="Pais",
            hover_data={
                "Ticker": True,
                "IV_Score": ":.1f",
                "Senal": True,
                "Vol_Asim": ":.2f",
                "Vol_Total": ":.2f",
                "Devaluacion": ":.2f",
                "Tendencia": True,
                "ISO": False,
            },
            title="<b>Mapa de Vulnerabilidad Estructural (IV Score)</b>",
            locationmode="ISO-3",
        )
        fig_map.update_layout(
            margin=dict(l=0, r=0, t=42, b=0),
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
                ticktext=["0 Estable", "25", "50 Alerta", "75", "100 Critico"],
            ),
            **base_layout,
        )

        fig_radar = go.Figure()
        for region in df["Region"].dropna().unique():
            df_reg = df[df["Region"] == region].sort_values("Pais")
            if df_reg.empty:
                continue

            paises = df_reg["Pais"].tolist()
            scores = df_reg["IV_Score"].tolist()
            r_vals = scores + [scores[0]]
            theta_vals = paises + [paises[0]]
            color = COLORES_REGION.get(region, "#FFFFFF")

            fig_radar.add_trace(
                go.Scatterpolar(
                    r=r_vals,
                    theta=theta_vals,
                    fill="toself",
                    fillcolor=_hex_to_rgba(color, 0.2),
                    name=region,
                    line=dict(color=color, width=2),
                    hovertemplate="<b>%{theta}</b><br>IV Score: %{r:.1f}<extra></extra>",
                )
            )

        fig_radar.update_layout(
            polar=dict(
                bgcolor="#111827",
                radialaxis=dict(
                    range=[0, 100],
                    tickvals=[25, 50, 75, 100],
                    gridcolor="#30363d",
                    linecolor="#30363d",
                ),
                angularaxis=dict(gridcolor="#30363d", linecolor="#30363d"),
            ),
            title="<b>Radar Regional</b>",
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=-0.18,
                xanchor="center",
                x=0.5,
            ),
            **base_layout,
        )

        return fig_map, fig_radar


analytics = RVMAnalytics()


__all__ = [
    "ACTIVOS",
    "RVMAnalytics",
    "UmbralesRVM",
    "PesosRVM",
    "analytics",
    "limpiar_cache",
]
