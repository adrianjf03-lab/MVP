from __future__ import annotations

from html import escape
from typing import Any

import streamlit as st

st.set_page_config(page_title="FirstFolio", page_icon="🔭", layout="wide")

import motor_datos
import rvm_logic


TOPIC_OPTIONS: dict[str, str] = {
    "Inteligencia Artificial": "Artificial Intelligence",
    "Semiconductores": "Semiconductors",
    "Blockchain": "Cryptocurrency",
    "Vehículos Eléctricos": "Electric Vehicles",
}

RVM_STATE_KEYS = ("rvm_data", "rvm_top_risk", "rvm_figs", "rvm_last_error")


def aplicar_estilos_css() -> None:
    """Inyecta el CSS global de la aplicación."""
    st.markdown(
        """
        <style>
            :root {
                --ff-bg: #0e1117;
                --ff-panel: #161b22;
                --ff-panel-2: #1a1f25;
                --ff-border: #30363d;
                --ff-text: #e6edf3;
                --ff-muted: #8b949e;
                --ff-cyan: #00e5ff;
                --ff-green: #2ea043;
                --ff-red: #f85149;
                --ff-yellow: #d29922;
            }

            .stApp {
                background-color: var(--ff-bg);
                color: var(--ff-text);
            }

            h1, h2, h3 {
                color: var(--ff-cyan) !important;
                letter-spacing: 0;
            }

            .stMetric {
                background-color: var(--ff-panel);
                padding: 14px;
                border-radius: 8px;
                border: 1px solid var(--ff-border);
            }

            div[data-testid="stExpander"] {
                background-color: var(--ff-panel-2);
                border: 1px solid var(--ff-border);
                border-radius: 8px;
            }

            .ff-caption {
                color: var(--ff-muted);
                font-size: 0.88rem;
            }

            .sentimiento-positivo,
            .sentimiento-negativo,
            .sentimiento-neutro {
                display: inline-block;
                font-weight: 800;
                padding: 2px 8px;
                border-radius: 999px;
            }

            .sentimiento-positivo {
                color: var(--ff-green);
                background-color: rgba(46, 160, 67, 0.15);
            }

            .sentimiento-negativo {
                color: var(--ff-red);
                background-color: rgba(248, 81, 73, 0.15);
            }

            .sentimiento-neutro {
                color: var(--ff-muted);
                background-color: rgba(139, 148, 158, 0.15);
            }

            .tesis-box {
                border-left: 4px solid var(--ff-cyan);
                padding: 8px 0 8px 14px;
                margin-top: 10px;
                color: #c9d1d9;
                background: rgba(0, 229, 255, 0.04);
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def inicializar_estado() -> None:
    """Inicializa variables de sesión para evitar pérdida de datos en re-runs."""
    st.session_state.setdefault("noticias_cache", {})
    st.session_state.setdefault("rvm_data", None)
    st.session_state.setdefault("rvm_top_risk", None)
    st.session_state.setdefault("rvm_figs", None)
    st.session_state.setdefault("rvm_last_error", None)


def _resetear_estado_rvm() -> None:
    for key in RVM_STATE_KEYS:
        st.session_state[key] = None


def _safe_text(value: Any, default: str = "") -> str:
    return escape(str(value if value is not None else default))


def _safe_hype(value: Any) -> int:
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return 50


def _sentiment_class(sentimiento: str) -> str:
    normalizado = (sentimiento or "neutro").strip().lower()
    if normalizado not in {"positivo", "negativo", "neutro"}:
        normalizado = "neutro"
    return f"sentimiento-{normalizado}"


def _render_hype_bar(hype: int) -> None:
    if hype >= 70:
        texto = f"Hype: {hype}/100 | Riesgo FOMO / sobreestimación de corto plazo"
    elif hype <= 39:
        texto = f"Hype: {hype}/100 | Posible subestimación de largo plazo"
    else:
        texto = f"Hype: {hype}/100 | Expectativas equilibradas"
    st.progress(hype, text=texto)


def renderizar_tab_ia() -> None:
    """Renderiza el módulo del Radar Cuantitativo de Sentimiento."""
    st.header("Radar Cuantitativo de Sentimiento")
    st.markdown("Agentes de IA analizando impacto mediático, Hype y valor informativo.")

    with st.expander("ℹ️ ¿Cómo funciona el motor de IA?"):
        st.write(
            """
            FirstFolio escanea noticias tecnológicas recientes, extrae empresas cotizadas
            y aplica un análisis escéptico inspirado en la Ley de Amara: solemos
            sobreestimar el impacto de la tecnología en el corto plazo y subestimarlo
            en el largo plazo.
            """
        )
        st.info(
            """
            **Lectura operativa:** el semáforo resume el tono de la noticia, mientras
            que el nivel de Hype mide riesgo de narrativa, FOMO y expectativas no
            verificadas.
            """
        )

    col_topic, col_button = st.columns([3, 1])
    with col_topic:
        tema_es = st.selectbox(
            "Selecciona sector para escanear",
            list(TOPIC_OPTIONS.keys()),
            label_visibility="collapsed",
        )
        tema_en = TOPIC_OPTIONS[tema_es]
    with col_button:
        escanear_btn = st.button(
            "📡 Escanear Mercado",
            use_container_width=True,
            type="primary",
        )

    if escanear_btn:
        with st.spinner(f"Agentes procesando {tema_es} en paralelo..."):
            try:
                resultados = motor_datos.obtener_noticias_ia(tema_en)
            except motor_datos.ConfiguracionError as exc:
                st.error(str(exc))
                resultados = []
            except Exception as exc:
                st.error(f"No se pudo completar el análisis de noticias: {exc}")
                resultados = []
            st.session_state.noticias_cache[tema_en] = resultados

    if tema_en not in st.session_state.noticias_cache:
        st.caption("Ejecuta el escáner para cargar noticias recientes del sector.")
        return

    noticias = st.session_state.noticias_cache[tema_en]
    if not noticias:
        st.warning(
            "No se encontraron empresas cotizadas claras en las noticias recientes "
            "o los proveedores externos no devolvieron datos suficientes."
        )
        return

    st.markdown("---")
    col_news, col_data = st.columns([6, 4])

    with col_news:
        st.subheader("📰 Flujo de análisis")
        for noti in noticias:
            titulo = _safe_text(noti.get("titulo"), "Noticia sin título")
            fuente = _safe_text(noti.get("fuente"), "Desconocida")
            ticker = _safe_text(noti.get("ticker_relacionado"), "N/D")
            url = noti.get("url")

            with st.container(border=True):
                st.markdown(f"**{titulo}**")
                st.caption(f"Fuente: {fuente} | Ticker extraído: `{ticker}`")
                if url:
                    st.link_button("Abrir fuente", str(url), use_container_width=False)

                sentimiento = str(noti.get("ia_sentimiento", "Neutro"))
                color_clase = _sentiment_class(sentimiento)
                hype = _safe_hype(noti.get("ia_hype", 50))
                fase = _safe_text(noti.get("ia_fase"), "Expectativas Equilibradas")
                razon = _safe_text(noti.get("ia_razon"), "Sin análisis disponible.")

                with st.expander("🔬 Veredicto del analista cuantitativo"):
                    st.markdown(
                        f"Sentimiento: <span class='{color_clase}'>{_safe_text(sentimiento.upper())}</span>",
                        unsafe_allow_html=True,
                    )
                    _render_hype_bar(hype)
                    st.markdown(f"**Fase detectada:** `{fase}`")
                    st.markdown(
                        f"<div class='tesis-box'><b>Tesis IA:</b> {razon}</div>",
                        unsafe_allow_html=True,
                    )

    with col_data:
        st.subheader("📊 Cotización reciente")
        tickers = sorted({str(n.get("ticker_relacionado", "")).upper() for n in noticias})
        for ticker in tickers:
            if not ticker:
                continue
            datos = motor_datos.obtener_datos_accion(ticker)
            if datos:
                st.metric(
                    label=f"Acción: {ticker}",
                    value=f"${datos['precio_actual']:,.2f}",
                    delta=f"{datos['variacion_pct']:+.2f}% (último cierre)",
                )
            else:
                st.metric(label=f"Acción: {ticker}", value="No disponible", delta="-")


def renderizar_tab_rvm() -> None:
    """Renderiza el Radar de Vulnerabilidad Macro-Financiera."""
    st.header("Radar de Vulnerabilidad Macro (RVM 4.2)")
    st.markdown(
        "Downside risk cambiario calculado con retornos logarítmicos orientados a "
        "depreciación, volatilidad asimétrica y normalización Z-Score."
    )
    st.info(
        "**Tip FirstFolio:** si el mapa global entra en zonas de alerta, reduce "
        "apalancamiento, revisa liquidez y evita extrapolar narrativas de corto plazo."
    )

    col_run, col_clear = st.columns([2, 1])
    ejecutar = col_run.button(
        "🔄 Ejecutar escáner de riesgo global",
        use_container_width=True,
        type="primary",
    )
    limpiar = col_clear.button("Limpiar caché RVM", use_container_width=True)

    if limpiar:
        _resetear_estado_rvm()
        rvm_logic.limpiar_cache()
        st.success("Caché RVM limpiada.")

    if ejecutar:
        with st.spinner("Descargando series, calculando downside risk y normalizando IV Scores..."):
            try:
                df_raw = rvm_logic.analytics.obtener_datos()
                if df_raw.empty:
                    raise ValueError("No hay datos suficientes para construir el RVM.")

                df_proc = rvm_logic.analytics.calcular_iv_score(df_raw)
                st.session_state.rvm_data = df_proc
                st.session_state.rvm_top_risk = (
                    df_proc.sort_values("IV_Score", ascending=False).iloc[0]
                )
                st.session_state.rvm_figs = rvm_logic.analytics.generar_graficos(df_proc)
                st.session_state.rvm_last_error = None
            except Exception as exc:
                _resetear_estado_rvm()
                st.session_state.rvm_last_error = str(exc)

    if st.session_state.rvm_last_error:
        st.error(f"No se pudo ejecutar el RVM: {st.session_state.rvm_last_error}")
        return

    if st.session_state.rvm_data is None:
        st.caption("Ejecuta el escáner para generar la matriz macro-financiera.")
        return

    top_risk = st.session_state.rvm_top_risk
    df_proc = st.session_state.rvm_data
    fig_map, fig_radar = st.session_state.rvm_figs

    c1, c2, c3 = st.columns(3)
    c1.metric(
        "Mayor riesgo detectado",
        top_risk["Pais"],
        f"IV: {top_risk['IV_Score']:.1f}",
        help="El IV Score combina volatilidad asimétrica, volatilidad total, devaluación anual y anormalidad Z-Score.",
    )
    c2.metric(
        "Nivel de alerta",
        top_risk["Senal"],
        help="Crítico >= 60 | Alerta >= 40 | Estable < 40.",
    )
    c3.metric(
        "Tendencia 30d",
        top_risk["Tendencia"],
        help="Evaluada con regresión lineal sobre log-precios orientados por dirección de riesgo.",
    )

    col_g1, col_g2 = st.columns([3, 2])
    with col_g1:
        st.plotly_chart(fig_map, use_container_width=True)
    with col_g2:
        st.plotly_chart(fig_radar, use_container_width=True)

    with st.expander("📂 Ver matriz de datos cuantitativos"):
        columnas = [
            "Region",
            "Pais",
            "ISO",
            "IV_Score",
            "Senal",
            "Vol_Asim",
            "Vol_Total",
            "Devaluacion",
            "Z_Score_Current",
            "R2",
        ]
        matriz_rvm = (
            df_proc[columnas]
            .sort_values("IV_Score", ascending=False)
            .reset_index(drop=True)
        )
        st.dataframe(
            matriz_rvm,
            use_container_width=True,
            hide_index=True,
            column_config={
                "IV_Score": st.column_config.ProgressColumn(
                    "IV Score",
                    help="Índice de vulnerabilidad normalizado en escala 0-100.",
                    min_value=0,
                    max_value=100,
                    format="%.1f",
                ),
                "Vol_Asim": st.column_config.NumberColumn(
                    "Vol. Asim.",
                    help="Downside volatility anualizada.",
                    format="%.2f%%",
                ),
                "Vol_Total": st.column_config.NumberColumn(
                    "Vol. Total",
                    help="Volatilidad total anualizada.",
                    format="%.2f%%",
                ),
                "Devaluacion": st.column_config.NumberColumn(
                    "Devaluación",
                    help="Depreciación anual orientada por dirección de riesgo.",
                    format="%.2f%%",
                ),
                "Z_Score_Current": st.column_config.NumberColumn(
                    "Z-Score 30d",
                    help="Anormalidad de la downside volatility reciente.",
                    format="%.2f",
                ),
                "R2": st.column_config.NumberColumn(
                    "R²",
                    help="Calidad explicativa de la tendencia lineal reciente.",
                    format="%.2f",
                ),
            },
        )


def renderizar_tab_aula() -> None:
    """Renderiza el aula virtual y simuladores educativos."""
    st.header("🎓 Aula Virtual: mercado de valores y primera operativa")
    st.markdown(
        "**Enfoque:** aprendizaje interactivo, prevención del sesgo narrativo y "
        "simulación de decisiones bajo incertidumbre."
    )

    with st.expander("🧱 Módulo 1: La base de todo y el ecosistema bursátil"):
        st.warning(
            "La mayoría cree que el mayor riesgo financiero es invertir y perder. "
            "En realidad, el riesgo garantizado es no proteger el poder adquisitivo "
            "frente a la inflación."
        )
        st.markdown("🧊 **Analogía del cubito de hielo**")
        st.write(
            "Imagina que tus ahorros son un cubito de hielo. Si permanecen inmóviles "
            "bajo el calor del coste de vida, se derriten lentamente."
        )
        st.markdown("🌱 **La solución: inversión disciplinada**")
        st.write(
            "Invertir no es apostar: es asignar capital a activos productivos con "
            "una tesis, horizonte temporal y gestión de riesgo."
        )
        st.info(
            """
            **Tu equipo en este ecosistema:**
            * **Empresa:** necesita capital para crecer.
            * **Inversor:** aporta capital a cambio de participación económica.
            * **Bróker:** conecta tus órdenes con el mercado.
            * **Regulador:** supervisa transparencia y abuso de mercado.
            """
        )

    with st.expander("🛡️ Módulo 2: El duelo entre acción individual y ETF"):
        st.write(
            """
            Una acción concentra riesgo idiosincrático. Un ETF reparte la exposición
            entre múltiples compañías, reduciendo el impacto de un fallo aislado.
            """
        )
        st.markdown("---")
        st.subheader("💥 Simulador de shock de mercado")

        gravedad = st.slider(
            "Selecciona la gravedad del reporte negativo",
            1,
            5,
            3,
            help="1 = leve, 5 = pánico de mercado.",
        )

        if st.button("Simular impacto", type="primary"):
            caida_accion = gravedad * 8.5
            caida_etf = gravedad * 0.8
            saldo_accion = 10_000 * (1 - caida_accion / 100)
            saldo_etf = 10_000 * (1 - caida_etf / 100)

            col1, col2 = st.columns(2)
            with col1:
                st.metric(
                    label="📉 Cartera 1: acción individual",
                    value=f"${saldo_accion:,.2f}",
                    delta=f"-{caida_accion:.1f}% riesgo concentrado",
                    delta_color="inverse",
                )
            with col2:
                st.metric(
                    label="🛡️ Cartera 2: ETF sectorial",
                    value=f"${saldo_etf:,.2f}",
                    delta=f"-{caida_etf:.1f}% diversificado",
                    delta_color="inverse",
                )
            st.success(
                "El ETF amortigua el impacto porque diluye el riesgo específico "
                "de una sola empresa dentro de una canasta diversificada."
            )

    with st.expander("⚙️ Módulo 3: Mecánica del mercado"):
        st.subheader("🎮 Misión del simulador: ejecuta tu compra")
        col_bid, col_ask = st.columns(2)
        col_bid.metric("💰 BID", "$99.50", help="Precio que ofrecen compradores.")
        col_ask.metric("🏷️ ASK", "$100.50", help="Precio que exigen vendedores.")

        tipo_orden = st.radio(
            "Elige tu instrucción para el bróker:",
            ["A Mercado", "Limitada"],
            help=(
                "A mercado prioriza ejecución inmediata. "
                "Limitada prioriza precio máximo o mínimo."
            ),
        )

        precio_limite = 0.0
        if tipo_orden == "Limitada":
            precio_limite = st.number_input(
                "Precio máximo a pagar ($):",
                min_value=1.0,
                value=99.00,
                step=0.10,
            )

        if st.button("🚀 Enviar orden", type="primary"):
            if tipo_orden == "A Mercado":
                st.success("✅ Orden ejecutada al instante por $100.50.")
            elif precio_limite >= 100.50:
                st.success(
                    f"✅ Orden ejecutada: ofreciste ${precio_limite:.2f}, "
                    "pero se ejecutó al mejor precio disponible: $100.50."
                )
            else:
                st.warning(
                    f"⏳ Orden pendiente: tu oferta de ${precio_limite:.2f} "
                    "queda esperando contraparte."
                )

    st.markdown("---")
    st.subheader("🏆 Evaluación final")
    with st.form("quiz_form"):
        q1 = st.radio(
            "1. Noticia con Hype 100/100. ¿Qué haces?",
            [
                "a) Comprar usando orden a mercado.",
                "b) Evaluar riesgo de sobreestimación.",
                "c) Invertir todo en instrumentos sin riesgo.",
            ],
        )
        q2 = st.radio(
            "2. Estás dispuesto a pagar un precio máximo. ¿Qué orden utilizas?",
            ["a) Orden a mercado.", "b) Stop-loss.", "c) Orden limitada."],
        )

        enviado = st.form_submit_button("✅ Enviar respuestas")
        if enviado:
            if q1.startswith("b") and q2.startswith("c"):
                st.success("🎉 Correcto. Priorizaste análisis y control de precio.")
            else:
                st.error("Revisa las lecciones: hay al menos una respuesta incorrecta.")


def main() -> None:
    aplicar_estilos_css()
    inicializar_estado()

    with st.sidebar:
        st.title("FirstFolio 🔭")
        st.caption("Plataforma de inteligencia financiera")
        st.info(
            "MVP con IA generativa, análisis macro-financiero y simuladores "
            "educativos para inversores minoristas."
        )

    tab1, tab2, tab3 = st.tabs(
        ["🚀 Radar de Oportunidades (IA)", "🌍 Monitor de Riesgo (RVM)", "🎓 Aula Virtual"]
    )

    with tab1:
        renderizar_tab_ia()
    with tab2:
        renderizar_tab_rvm()
    with tab3:
        renderizar_tab_aula()


if __name__ == "__main__":
    main()
