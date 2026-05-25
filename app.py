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
    st.header("🎓 Aula Virtual: de cero a una decisión informada")
    st.markdown(
        "Un recorrido práctico para entender el mercado, reconocer sesgos y leer "
        "los radares de FirstFolio sin depender de titulares ni corazonadas."
    )

    ruta_cols = st.columns(4)
    ruta_cols[0].metric("1", "Fundamentos", "Inflación y activos")
    ruta_cols[1].metric("2", "Radares", "IA + RVM")
    ruta_cols[2].metric("3", "Simulación", "Órdenes y shocks")
    ruta_cols[3].metric("4", "Checklist", "Decisión final")

    aula_fund, aula_radares, aula_sim, aula_eval = st.tabs(
        [
            "🧱 Fundamentos",
            "📡 Leer radares",
            "🎮 Simuladores",
            "🏁 Checklist final",
        ]
    )

    with aula_fund:
        st.subheader("Antes de invertir: qué problema estás intentando resolver")
        st.write(
            "Invertir no empieza preguntando qué acción comprar. Empieza con una "
            "pregunta más básica: cómo proteger y hacer crecer tu poder adquisitivo "
            "sin asumir riesgos que no entiendes."
        )

        with st.expander("1. Inflación: el riesgo invisible", expanded=True):
            st.warning(
                "Guardar dinero sin invertir puede parecer seguro, pero si los precios "
                "suben cada año, ese dinero compra menos bienes y servicios."
            )

            col_a, col_b, col_c = st.columns(3)
            ahorro_inicial = col_a.number_input(
                "Ahorro inicial",
                min_value=100,
                max_value=1_000_000,
                value=10_000,
                step=500,
                key="aula_ahorro_inicial",
            )
            inflacion = col_b.slider(
                "Inflación anual estimada",
                0.0,
                12.0,
                4.0,
                0.5,
                format="%.1f%%",
                key="aula_inflacion",
            )
            anos = col_c.slider(
                "Horizonte",
                1,
                30,
                10,
                key="aula_horizonte_inflacion",
            )

            poder_futuro = ahorro_inicial / ((1 + inflacion / 100) ** anos)
            perdida_poder = 1 - (poder_futuro / ahorro_inicial)
            col_res1, col_res2 = st.columns(2)
            col_res1.metric(
                "Poder adquisitivo equivalente",
                f"${poder_futuro:,.0f}",
                help="Cuánto compraría tu dinero actual al final del periodo.",
            )
            col_res2.metric(
                "Pérdida de poder de compra",
                f"{perdida_poder * 100:.1f}%",
                delta_color="inverse",
            )
            st.info(
                "La inversión busca que tu capital trabaje lo suficiente para compensar "
                "inflación, impuestos y errores de comportamiento."
            )

        with st.expander("2. Las piezas básicas del mercado"):
            st.write(
                "Cada activo combina tres variables: rendimiento esperado, riesgo y "
                "liquidez. No existe un activo perfecto; existe una mezcla adecuada "
                "para un objetivo concreto."
            )
            st.dataframe(
                [
                    {
                        "Instrumento": "Acción",
                        "Qué compras": "Una participación en una empresa",
                        "Riesgo principal": "La empresa puede decepcionar o caer fuerte",
                        "Uso razonable": "Crecimiento con horizonte largo",
                    },
                    {
                        "Instrumento": "ETF",
                        "Qué compras": "Una canasta de activos",
                        "Riesgo principal": "Riesgo del mercado o sector completo",
                        "Uso razonable": "Diversificación simple y eficiente",
                    },
                    {
                        "Instrumento": "Bono",
                        "Qué compras": "Deuda de gobierno o empresa",
                        "Riesgo principal": "Impago, inflación o subida de tipos",
                        "Uso razonable": "Ingresos, estabilidad y planificación",
                    },
                    {
                        "Instrumento": "Efectivo",
                        "Qué compras": "Liquidez inmediata",
                        "Riesgo principal": "Pérdida por inflación",
                        "Uso razonable": "Fondo de emergencia y oportunidades",
                    },
                ],
                use_container_width=True,
                hide_index=True,
            )

        with st.expander("3. Riesgo, volatilidad y drawdown"):
            st.markdown(
                """
                **Volatilidad** es cuánto se mueve el precio. **Riesgo** es la
                posibilidad de no cumplir tu objetivo financiero. Una inversión puede
                moverse mucho y aun así ser razonable si tienes horizonte, liquidez y
                una tesis sólida.

                **Drawdown** es la caída desde un máximo hasta un mínimo. Es importante
                porque las pérdidas grandes exigen subidas todavía mayores para
                recuperarse.
                """
            )
            st.dataframe(
                [
                    {"Caída": "-10%", "Subida necesaria para recuperar": "+11.1%"},
                    {"Caída": "-25%", "Subida necesaria para recuperar": "+33.3%"},
                    {"Caída": "-50%", "Subida necesaria para recuperar": "+100.0%"},
                    {"Caída": "-70%", "Subida necesaria para recuperar": "+233.3%"},
                ],
                use_container_width=True,
                hide_index=True,
            )
            st.success(
                "Idea clave: protegerte de pérdidas irreversibles suele ser más "
                "importante que perseguir cada oportunidad."
            )

        with st.expander("4. Sesgos que FirstFolio intenta combatir"):
            st.dataframe(
                [
                    {
                        "Sesgo": "FOMO",
                        "Cómo aparece": "Comprar porque todos hablan de un activo",
                        "Defensa": "Revisar Hype, precio y evidencia verificable",
                    },
                    {
                        "Sesgo": "Confirmación",
                        "Cómo aparece": "Buscar solo noticias que apoyan tu idea",
                        "Defensa": "Leer señales negativas y escenarios alternativos",
                    },
                    {
                        "Sesgo": "Recencia",
                        "Cómo aparece": "Creer que lo último seguirá ocurriendo",
                        "Defensa": "Comparar corto plazo con datos históricos",
                    },
                    {
                        "Sesgo": "Exceso de confianza",
                        "Cómo aparece": "Invertir demasiado en una sola tesis",
                        "Defensa": "Limitar tamaño de posición y diversificar",
                    },
                ],
                use_container_width=True,
                hide_index=True,
            )

    with aula_radares:
        st.subheader("Cómo interpretar FirstFolio sin ser analista profesional")
        st.write(
            "Los radares no intentan adivinar el futuro. Ordenan señales para que "
            "puedas hacer mejores preguntas antes de asumir riesgo."
        )

        with st.expander("1. Radar de Oportunidades IA: sentimiento no es recomendación", expanded=True):
            st.markdown(
                """
                El Radar IA lee noticias y separa tres cosas que suelen mezclarse:
                **tono de la noticia**, **nivel de narrativa** y **calidad de la tesis**.
                Una noticia positiva con Hype alto puede ser más peligrosa que una
                noticia aburrida con fundamentos sólidos.
                """
            )
            st.dataframe(
                [
                    {
                        "Campo": "Sentimiento",
                        "Qué significa": "Impacto aparente de la noticia sobre la empresa",
                        "Cómo usarlo": "Identifica si el titular favorece o perjudica al activo",
                    },
                    {
                        "Campo": "Hype",
                        "Qué significa": "Intensidad narrativa y riesgo de euforia",
                        "Cómo usarlo": "Cuanto más alto, más conviene exigir datos duros",
                    },
                    {
                        "Campo": "Fase Amara",
                        "Qué significa": "Sobreestimación de corto plazo o subestimación estructural",
                        "Cómo usarlo": "Distingue moda inmediata de tendencia durable",
                    },
                    {
                        "Campo": "Tesis IA",
                        "Qué significa": "Resumen crítico de la noticia",
                        "Cómo usarlo": "Úsala como hipótesis, no como veredicto final",
                    },
                ],
                use_container_width=True,
                hide_index=True,
            )

            col_h1, col_h2 = st.columns([2, 1])
            hype_demo = col_h1.slider(
                "Prueba un nivel de Hype",
                0,
                100,
                75,
                key="aula_hype_demo",
            )
            sentimiento_demo = col_h2.selectbox(
                "Sentimiento",
                ["Positivo", "Neutro", "Negativo"],
                key="aula_sentimiento_demo",
            )

            if hype_demo >= 70 and sentimiento_demo == "Positivo":
                st.warning(
                    "Lectura educativa: entusiasmo alto. Antes de comprar, busca ventas, "
                    "márgenes, flujo de caja, valoración y catalizadores reales."
                )
            elif hype_demo <= 39:
                st.info(
                    "Lectura educativa: narrativa baja. Puede ser aburrido, pero vale "
                    "la pena revisar si hay mejora estructural ignorada por el mercado."
                )
            elif sentimiento_demo == "Negativo":
                st.error(
                    "Lectura educativa: noticia adversa. Distingue daño temporal de "
                    "deterioro permanente del negocio."
                )
            else:
                st.success(
                    "Lectura educativa: señal equilibrada. La decisión depende más de "
                    "valoración, horizonte y tamaño de posición."
                )

        with st.expander("2. Monitor de Riesgo RVM: qué significa el IV Score"):
            st.markdown(
                """
                El RVM observa vulnerabilidad macro-financiera en divisas. No analiza
                una empresa concreta: analiza si el entorno global está más frágil.
                Esto importa porque en mercados tensos aumenta la probabilidad de
                caídas rápidas, fuga a liquidez y ventas indiscriminadas.
                """
            )
            st.dataframe(
                [
                    {
                        "Métrica": "IV Score",
                        "Lectura simple": "Termómetro agregado de vulnerabilidad",
                        "Atención": "Por encima de 60 exige mucha prudencia",
                    },
                    {
                        "Métrica": "Vol. Asim.",
                        "Lectura simple": "Volatilidad en la dirección de depreciación",
                        "Atención": "Mide movimiento adverso, no solo ruido normal",
                    },
                    {
                        "Métrica": "Devaluación",
                        "Lectura simple": "Pérdida de valor de la divisa frente al USD",
                        "Atención": "Puede afectar inflación, deuda y capital extranjero",
                    },
                    {
                        "Métrica": "Z-Score 30d",
                        "Lectura simple": "Qué tan anormal es el estrés reciente",
                        "Atención": "Valores altos indican régimen inusual",
                    },
                    {
                        "Métrica": "Tendencia",
                        "Lectura simple": "Si el riesgo acelera o se relaja",
                        "Atención": "La dirección puede importar más que el nivel aislado",
                    },
                ],
                use_container_width=True,
                hide_index=True,
            )

            st.markdown("**Regla educativa de lectura rápida**")
            st.dataframe(
                [
                    {
                        "Señal": "🟢 Estable",
                        "Qué hacer": "Operar con disciplina normal",
                        "Pregunta clave": "¿La tesis depende de una narrativa exagerada?",
                    },
                    {
                        "Señal": "⚠️ Alerta",
                        "Qué hacer": "Reducir tamaño, evitar apalancamiento y exigir margen de seguridad",
                        "Pregunta clave": "¿Sobreviviría mi cartera a una caída rápida?",
                    },
                    {
                        "Señal": "🔴 Crítico",
                        "Qué hacer": "Priorizar liquidez, revisar stops y no perseguir subidas verticales",
                        "Pregunta clave": "¿Estoy tomando riesgo porque hay oportunidad o por ansiedad?",
                    },
                ],
                use_container_width=True,
                hide_index=True,
            )

            if st.session_state.rvm_data is not None:
                st.markdown("**Lectura aplicada con el último escaneo RVM**")
                top_riesgos = (
                    st.session_state.rvm_data[
                        ["Pais", "IV_Score", "Senal", "Tendencia", "Z_Score_Current"]
                    ]
                    .sort_values("IV_Score", ascending=False)
                    .head(3)
                    .reset_index(drop=True)
                )
                st.dataframe(
                    top_riesgos,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "IV_Score": st.column_config.ProgressColumn(
                            "IV Score",
                            min_value=0,
                            max_value=100,
                            format="%.1f",
                        ),
                        "Z_Score_Current": st.column_config.NumberColumn(
                            "Z-Score 30d",
                            format="%.2f",
                        ),
                    },
                )
                st.info(
                    "Si estos países concentran riesgo, no significa que todo vaya a "
                    "caer. Significa que conviene ser más selectivo y no confundir "
                    "rebotes de corto plazo con seguridad estructural."
                )
            else:
                st.caption(
                    "Ejecuta el Monitor de Riesgo para que aquí aparezca una lectura "
                    "educativa del último escaneo."
                )

        with st.expander("3. Cómo combinar Radar IA + RVM"):
            st.dataframe(
                [
                    {
                        "Radar IA": "Hype alto",
                        "RVM": "Crítico",
                        "Interpretación": "Euforia en entorno frágil",
                        "Conducta prudente": "Esperar, reducir tamaño o exigir gran margen de seguridad",
                    },
                    {
                        "Radar IA": "Hype bajo",
                        "RVM": "Estable",
                        "Interpretación": "Posible oportunidad menos concurrida",
                        "Conducta prudente": "Investigar fundamentos y valoración",
                    },
                    {
                        "Radar IA": "Negativo",
                        "RVM": "Alerta",
                        "Interpretación": "Riesgo específico y macro a la vez",
                        "Conducta prudente": "Evitar decisiones impulsivas y revisar exposición total",
                    },
                    {
                        "Radar IA": "Equilibrado",
                        "RVM": "Estable",
                        "Interpretación": "Condiciones menos tensas",
                        "Conducta prudente": "Planificar entrada, salida y tamaño antes de operar",
                    },
                ],
                use_container_width=True,
                hide_index=True,
            )

    with aula_sim:
        st.subheader("Simuladores: aprende con números antes de usar dinero real")

        with st.expander("1. Acción individual vs ETF ante una mala noticia", expanded=True):
            capital = st.number_input(
                "Capital simulado",
                min_value=500,
                max_value=250_000,
                value=10_000,
                step=500,
                key="aula_capital_shock",
            )
            gravedad = st.slider(
                "Gravedad del reporte negativo",
                1,
                5,
                3,
                help="1 = leve, 5 = pánico de mercado.",
                key="aula_gravedad_shock",
            )
            concentracion = st.slider(
                "Peso de una sola acción en tu cartera",
                5,
                100,
                40,
                step=5,
                format="%d%%",
                key="aula_concentracion",
            )

            caida_accion = gravedad * 8.5
            caida_etf = gravedad * 0.8
            perdida_concentrada = capital * (concentracion / 100) * (caida_accion / 100)
            perdida_etf = capital * (caida_etf / 100)
            saldo_accion = capital - perdida_concentrada
            saldo_etf = capital - perdida_etf

            col1, col2 = st.columns(2)
            with col1:
                st.metric(
                    label="Cartera con acción concentrada",
                    value=f"${saldo_accion:,.2f}",
                    delta=f"-${perdida_concentrada:,.2f}",
                    delta_color="inverse",
                )
            with col2:
                st.metric(
                    label="Cartera diversificada con ETF",
                    value=f"${saldo_etf:,.2f}",
                    delta=f"-${perdida_etf:,.2f}",
                    delta_color="inverse",
                )
            st.info(
                "La diversificación no elimina el riesgo, pero evita que un solo error "
                "domine toda la cartera."
            )

        with st.expander("2. Órdenes de mercado y órdenes limitadas"):
            st.write(
                "Una buena tesis puede ejecutarse mal si no entiendes el tipo de orden. "
                "La orden a mercado prioriza velocidad; la limitada prioriza precio."
            )
            col_bid, col_ask = st.columns(2)
            col_bid.metric("BID", "$99.50", help="Precio que ofrecen compradores.")
            col_ask.metric("ASK", "$100.50", help="Precio que exigen vendedores.")

            tipo_orden = st.radio(
                "Elige tu instrucción para el bróker:",
                ["A Mercado", "Limitada"],
                help=(
                    "A mercado prioriza ejecución inmediata. "
                    "Limitada prioriza precio máximo o mínimo."
                ),
                key="aula_tipo_orden",
            )

            precio_limite = 0.0
            if tipo_orden == "Limitada":
                precio_limite = st.number_input(
                    "Precio máximo a pagar ($):",
                    min_value=1.0,
                    value=99.00,
                    step=0.10,
                    key="aula_precio_limite",
                )

            if st.button("🚀 Enviar orden simulada", type="primary", key="aula_enviar_orden"):
                if tipo_orden == "A Mercado":
                    st.success("Orden ejecutada al instante por $100.50.")
                    st.warning(
                        "Aceptaste el precio disponible. En activos ilíquidos, esa "
                        "comodidad puede salir cara por spread o deslizamiento."
                    )
                elif precio_limite >= 100.50:
                    st.success(
                        f"Orden ejecutada: ofreciste ${precio_limite:.2f}, "
                        "pero se ejecutó al mejor precio disponible: $100.50."
                    )
                else:
                    st.info(
                        f"Orden pendiente: tu oferta de ${precio_limite:.2f} queda "
                        "esperando a que un vendedor acepte ese precio."
                    )

        with st.expander("3. Tamaño de posición: cuánto arriesgar"):
            st.write(
                "La pregunta no es solo si una idea es buena. También importa cuánto "
                "puedes perder si estás equivocado."
            )
            cartera = st.number_input(
                "Valor total de cartera",
                min_value=1_000,
                max_value=1_000_000,
                value=25_000,
                step=1_000,
                key="aula_valor_cartera",
            )
            riesgo_pct = st.slider(
                "Riesgo máximo aceptado por idea",
                0.25,
                5.0,
                1.0,
                0.25,
                format="%.2f%%",
                key="aula_riesgo_por_idea",
            )
            distancia_stop = st.slider(
                "Distancia hasta punto de invalidación",
                2.0,
                40.0,
                12.0,
                1.0,
                format="%.0f%%",
                key="aula_distancia_stop",
            )

            perdida_max = cartera * riesgo_pct / 100
            posicion_max = perdida_max / (distancia_stop / 100)
            peso_cartera = min(100.0, posicion_max / cartera * 100)

            col_p1, col_p2, col_p3 = st.columns(3)
            col_p1.metric("Pérdida máxima", f"${perdida_max:,.2f}")
            col_p2.metric("Posición máxima", f"${posicion_max:,.2f}")
            col_p3.metric("Peso aproximado", f"{peso_cartera:.1f}%")
            st.success(
                "El tamaño de posición convierte una opinión incierta en un riesgo "
                "controlado. Esa es una de las diferencias entre invertir y apostar."
            )

    with aula_eval:
        st.subheader("Checklist de decisión antes de invertir")
        st.write(
            "Este checklist transforma los radares en una conversación ordenada contigo "
            "mismo antes de pulsar comprar."
        )

        checks = {
            "Entiendo qué compra realmente el activo.": st.checkbox(
                "Entiendo qué compra realmente el activo.",
                key="check_activo",
            ),
            "Sé por qué podría subir y por qué podría caer.": st.checkbox(
                "Sé por qué podría subir y por qué podría caer.",
                key="check_tesis",
            ),
            "He revisado si el Hype me está empujando a actuar rápido.": st.checkbox(
                "He revisado si el Hype me está empujando a actuar rápido.",
                key="check_hype",
            ),
            "He mirado el RVM para entender el contexto macro.": st.checkbox(
                "He mirado el RVM para entender el contexto macro.",
                key="check_rvm",
            ),
            "Tengo definido tamaño de posición y punto de invalidación.": st.checkbox(
                "Tengo definido tamaño de posición y punto de invalidación.",
                key="check_riesgo",
            ),
            "Puedo soportar la pérdida sin afectar mi vida financiera.": st.checkbox(
                "Puedo soportar la pérdida sin afectar mi vida financiera.",
                key="check_perdida",
            ),
        }
        completados = sum(checks.values())
        st.progress(completados / len(checks), text=f"{completados}/{len(checks)} criterios completados")

        if completados <= 2:
            st.error(
                "Nivel de preparación bajo. La operación todavía depende demasiado "
                "de intuición o entusiasmo."
            )
        elif completados <= 4:
            st.warning(
                "Preparación intermedia. Ya hay estructura, pero faltan piezas de "
                "control de riesgo."
            )
        else:
            st.success(
                "Buena preparación. Aun así, ninguna señal elimina incertidumbre: solo "
                "mejora la calidad de la decisión."
            )

        st.markdown("---")
        st.subheader("Evaluación rápida")
        with st.form("quiz_form"):
            q1 = st.radio(
                "1. Noticia positiva con Hype 95/100. ¿Qué haces primero?",
                [
                    "a) Comprar rápido antes de que suba más.",
                    "b) Buscar métricas verificables y riesgo de sobreestimación.",
                    "c) Ignorar siempre cualquier noticia positiva.",
                ],
                key="quiz_q1",
            )
            q2 = st.radio(
                "2. El RVM marca riesgo crítico. ¿Qué cambia?",
                [
                    "a) Nada, porque solo importan las acciones individuales.",
                    "b) Conviene revisar liquidez, tamaño y exposición total.",
                    "c) Hay que vender todo automáticamente.",
                ],
                key="quiz_q2",
            )
            q3 = st.radio(
                "3. Estás dispuesto a pagar un precio máximo. ¿Qué orden utilizas?",
                ["a) Orden a mercado.", "b) Stop-loss.", "c) Orden limitada."],
                key="quiz_q3",
            )
            q4 = st.radio(
                "4. ¿Qué significa diversificar?",
                [
                    "a) Comprar muchos activos sin entenderlos.",
                    "b) Repartir riesgos para que una sola tesis no domine la cartera.",
                    "c) Evitar cualquier pérdida.",
                ],
                key="quiz_q4",
            )

            enviado = st.form_submit_button("✅ Enviar respuestas")
            if enviado:
                aciertos = sum(
                    [
                        q1.startswith("b"),
                        q2.startswith("b"),
                        q3.startswith("c"),
                        q4.startswith("b"),
                    ]
                )
                st.metric("Resultado", f"{aciertos}/4")
                if aciertos == 4:
                    st.success("Excelente. Ya estás leyendo FirstFolio con criterio de riesgo.")
                elif aciertos >= 2:
                    st.warning("Vas bien. Repasa los módulos donde dudaste.")
                else:
                    st.error("Conviene volver a fundamentos antes de simular decisiones.")


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
