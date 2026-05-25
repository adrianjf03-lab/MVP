
from __future__ import annotations

import streamlit as st
import motor_datos  
import rvm_logic    

# --- CONFIGURACIÓN Y ESTILOS ---
st.set_page_config(page_title="FirstFolio", page_icon="🔭", layout="wide")

def aplicar_estilos_css() -> None:
    """Inyecta el CSS global de la aplicación."""
    st.markdown("""
    <style>
        .stApp { background-color: #0e1117; color: #e0e0e0; }
        h1, h2, h3 { color: #00e5ff !important; }
        .stMetric { background-color: #161b22; padding: 15px; border-radius: 10px; border: 1px solid #30363d; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
        div[data-testid="stExpander"] { background-color: #1a1f25; border: 1px solid #30363d; border-radius: 8px; }
        .sentimiento-positivo { color: #2ea043; font-weight: 800; background-color: rgba(46, 160, 67, 0.15); padding: 2px 8px; border-radius: 12px;}
        .sentimiento-negativo { color: #f85149; font-weight: 800; background-color: rgba(248, 81, 73, 0.15); padding: 2px 8px; border-radius: 12px;}
        .sentimiento-neutro { color: #8b949e; font-weight: 800; background-color: rgba(139, 148, 158, 0.15); padding: 2px 8px; border-radius: 12px;}
        .tesis-box { border-left: 4px solid #00e5ff; padding-left: 15px; margin-top: 10px; font-style: italic; color: #c9d1d9; }
    </style>
    """, unsafe_allow_html=True)

def inicializar_estado() -> None:
    """Inicializa las variables de sesión para evitar pérdida de datos en re-runs."""
    if "noticias_cache" not in st.session_state:
        st.session_state.noticias_cache = {}
    
    # Nuevo: Persistencia para el RVM
    if "rvm_data" not in st.session_state:
        st.session_state.rvm_data = None
    if "rvm_top_risk" not in st.session_state:
        st.session_state.rvm_top_risk = None
    if "rvm_figs" not in st.session_state:
        st.session_state.rvm_figs = None

# --- RENDERIZADO DE PESTAÑAS ---

def renderizar_tab_ia() -> None:
    """Renderiza el módulo del Radar Cuantitativo de Sentimiento."""
    st.header("Radar Cuantitativo de Sentimiento")
    st.markdown("Agentes de IA analizando el impacto mediático (Hype) vs. Valor Real.")
    
    with st.expander("ℹ️ ¿Cómo funciona nuestro Motor de IA? (Combatiendo el Ruido Mediático)"):
        st.write("""
        El mercado se mueve por noticias, pero no todo lo que brilla es oro. FirstFolio integra un motor de Inteligencia Artificial que escanea noticias tecnológicas mundiales para ayudarte a tomar decisiones sin dejarte llevar por las emociones.
        * **Semáforo de Sentimiento:** Nuestra IA te indica si el impacto para un activo específico es Positivo, Neutro o Negativo.
        * **Nivel de Hype (Ley de Amara):** Medimos el "Nivel de Hype" (0-100) para evitar que compres en el pico de la euforia mediática.
        """)

    opciones_tema = {
        "Inteligencia Artificial": "Artificial Intelligence",
        "Semiconductores": "Semiconductors",
        "Blockchain": "Cryptocurrency",
        "Vehículos Eléctricos": "Electric Vehicles"
    }
    
    c1, c2 = st.columns([3, 1])
    with c1:
        tema_es = st.selectbox("Selecciona Sector para Escanear:", list(opciones_tema.keys()), label_visibility="collapsed")
        tema_en = opciones_tema[tema_es]
    with c2:
        escanear_btn = st.button("📡 Escanear Mercado", use_container_width=True, type="primary")
    
    if escanear_btn:
        with st.spinner(f"Agentes procesando {tema_es} en paralelo... esto tomará unos segundos."):
            resultados = motor_datos.obtener_noticias_ia(tema_en)
            st.session_state.noticias_cache[tema_en] = resultados

    if tema_en in st.session_state.noticias_cache:
        noticias = st.session_state.noticias_cache[tema_en]
        
        if not noticias:
            st.warning("La IA no encontró empresas cotizadas claras (públicas) en las noticias recientes de este sector.")
            return

        st.markdown("---")
        col_news, col_data = st.columns([6, 4])
        
        with col_news:
            st.subheader("📰 Flujo de Análisis")
            for noti in noticias:
                with st.container():
                    st.markdown(f"**{noti['titulo']}**")
                    st.caption(f"Fuente: {noti['fuente']} | Ticker Extraído: `{noti['ticker_relacionado']}`")
                    
                    color_clase = f"sentimiento-{noti.get('ia_sentimiento', 'neutro').lower()}"
                    
                    with st.expander("🔬 Veredicto del Analista Cuantitativo", expanded=False):
                        st.markdown(f"Sentimiento: <span class='{color_clase}'>{noti.get('ia_sentimiento', 'NEUTRO').upper()}</span>", unsafe_allow_html=True)
                        
                        hype = noti.get('ia_hype', 50)
                        if hype > 70:
                            st.progress(hype, text=f"🔥 Hype: {hype}/100 ➔ ⚠️ Riesgo FOMO / Sobreestimación Corto Plazo")
                        elif hype < 40:
                            st.progress(hype, text=f"🧊 Hype: {hype}/100 ➔ 🌱 Posible Subestimación Largo Plazo")
                        else:
                            st.progress(hype, text=f"⚖️ Hype: {hype}/100 ➔ Expectativas Equilibradas")
                        
                        st.markdown(f"**Fase Detectada:** `{noti.get('ia_fase', 'Desconocida')}`")
                        st.markdown(f"<div class='tesis-box'><b>Tesis IA:</b> {noti.get('ia_razon', '')}</div>", unsafe_allow_html=True)

        with col_data:
            st.subheader("📊 Cotización en Vivo")
            for noti in noticias:
                ticker = noti['ticker_relacionado']
                datos = motor_datos.obtener_datos_accion(ticker)
                if datos:
                    st.metric(label=f"Acción: {ticker}", value=f"${datos['precio_actual']}", delta=f"{datos['variacion_pct']}% (5d)")
                else:
                    st.metric(label=f"Acción: {ticker}", value="No disp.", delta="-")

def renderizar_tab_rvm() -> None:
    """Renderiza el módulo del Radar de Vulnerabilidad Macrofinanciera con persistencia de estado."""
    st.header("Radar de Vulnerabilidad Macro (RVM 4.2)")
    st.markdown("Este módulo utiliza **Volatilidad Asimétrica** y normalización **Z-Score** para detectar crisis estructurales en divisas base.")
    st.info("💡 **Tip FirstFolio:** Revisa este mapa de calor. Si el mercado global está en rojo, opera con cautela.")
    
    if st.button("🔄 Ejecutar Escáner de Riesgo Global"):
        with st.spinner("Procesando IV Scores y normalizando Z-Scores..."):
            # M6: Corrección del nombre del objeto a 'analytics'
            df_raw = rvm_logic.analytics.obtener_datos()
            
            if not df_raw.empty:
                df_proc = rvm_logic.analytics.calcular_iv_score(df_raw)
                
                # C2: Persistencia en Session State
                st.session_state.rvm_data = df_proc
                st.session_state.rvm_top_risk = df_proc.sort_values('IV_Score', ascending=False).iloc[0]
                st.session_state.rvm_figs = rvm_logic.analytics.generar_graficos(df_proc)

    # Renderizado condicional basado en la caché
    if st.session_state.rvm_data is not None:
        top_risk = st.session_state.rvm_top_risk
        df_proc = st.session_state.rvm_data
        fig_map, fig_radar = st.session_state.rvm_figs
        
        c1, c2, c3 = st.columns(3)
        # U3: Tooltips incorporados
        c1.metric("Mayor Riesgo Detectado", top_risk['Pais'], f"IV: {top_risk['IV_Score']}", help="El IV Score combina volatilidad asimétrica, histórica y devaluación real.")
        c2.metric("Nivel de Alerta", top_risk['Senal'], help="🔴 Crítico (>60) | ⚠️ Alerta (>40) | 🟢 Estable (<40)")
        c3.metric("Tendencia (30d)", top_risk['Tendencia'], help="Evaluada mediante regresión lineal sobre los cierres de los últimos 30 días.")
        
        col_g1, col_g2 = st.columns([3, 2])
        # C1: Se usa use_container_width en lugar de width="stretch"
        with col_g1: 
            st.plotly_chart(fig_map, use_container_width=True)
        with col_g2: 
            st.plotly_chart(fig_radar, use_container_width=True)
        
        with st.expander("📂 Ver Matriz de Datos Cuantitativos"):
            st.dataframe(
                df_proc[['Pais', 'ISO', 'IV_Score', 'Senal', 'Vol_Asim', 'Devaluacion', 'Z_Score_Current']]
                .style.background_gradient(subset=['IV_Score'], cmap='RdYlGn_r')
                .format({"Vol_Asim": "{:.2f}%", "Devaluacion": "{:.2f}%", "Z_Score_Current": "{:.2f}"})
            )

def renderizar_tab_aula() -> None:
    """Renderiza el Aula Virtual integrando los Callouts (U5)."""
    st.header("🎓 Aula Virtual: El Mercado de Valores y tu Primera Operativa")
    st.markdown("**Enfoque:** Aprendizaje interactivo, prevención del riesgo (Ley de Amara) y simulación de operativa real.")

    with st.expander("🧱 Módulo 1: La Base de Todo y el Ecosistema Bursátil"):
        # U5: Uso de st.info / st.warning en lugar de texto plano
        st.warning("La mayoría de la gente cree que el mayor riesgo financiero es invertir y perderlo todo. En realidad, el único riesgo garantizado es **no hacer nada**. Te presentamos a tu enemigo silencioso: **La Inflación**.")

        st.markdown("🧊 **La Analogía del Cubito de Hielo:**")
        st.write("Imagina que tus ahorros son un cubito de hielo. Si los guardas bajo el colchón o en una cuenta bancaria tradicional, el calor del coste de vida hará que se derrita lentamente. Un billete de $100 hoy compra mucho menos que hace 10 años.")

        st.markdown("🌱 **La Solución (Inversión):**")
        st.write("Invertir no es apostar. Es tomar ese 'agua' y usarla para regar un manzano. El objetivo es que el árbol genere suficientes manzanas cada año para compensar lo que el calor te está robando.")

        st.info("""
        **Tu Equipo en este Ecosistema:**
        * 🏢 **La Empresa:** Necesita capital para construir fábricas o software.
        * 👥 **Tú (El Inversor):** Aportas capital a cambio de un "trozo" de esa empresa.
        * 🏦 **El Bróker:** El puente tecnológico que te conecta con el mercado.
        * ⚖️ **El Regulador:** El árbitro que asegura que nadie haga trampa.
        """)

    with st.expander("🛡️ Módulo 2: Segunda Misión - El Duelo (Acción vs. ETF)"):
        st.write("""
        En el mundo real, no es lo mismo apostar todo tu dinero a una sola carta que repartirlo. Tu objetivo en esta sesión será simular un escenario de crisis sectorial.
        * **Acción Individual:** Todo tu riesgo está concentrado. Si la empresa falla, sufres el impacto completo.
        * **ETF Sectorial:** Tienes una canasta de 100 empresas. Si una falla, las otras 99 amortiguan el golpe.
        """)
        st.markdown("---")
        st.subheader("💥 Simulador de Shock de Mercado")
        
        gravedad = st.slider("Selecciona la Gravedad del Reporte Negativo:", 1, 5, 3, help="1 = Leve, 5 = Pánico de Mercado")
        
        if st.button("Simular Impacto (Reporte de Ganancias)", type="primary"):
            caida_accion = gravedad * 8.5  
            caida_etf = gravedad * 0.8     
            
            saldo_accion = 10000 * (1 - caida_accion/100)
            saldo_etf = 10000 * (1 - caida_etf/100)
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric(label="📉 Cartera 1: Acción Individual", value=f"${saldo_accion:,.2f}", delta=f"-{caida_accion:.1f}% Riesgo Concentrado", delta_color="inverse")
            with col2:
                st.metric(label="🛡️ Cartera 2: ETF Sectorial", value=f"${saldo_etf:,.2f}", delta=f"-{caida_etf:.1f}% Diversificado", delta_color="inverse")
                
            st.success("**Análisis:** Observa cómo el ETF te brinda diversificación instantánea. El mal desempeño de una sola empresa se compensa con la estabilidad de las otras 99 en la canasta.")
    
    with st.expander("⚙️ Módulo 3: La Mecánica del Mercado (Cómo Comprar)"):
        st.subheader("🎮 Misión del Simulador: Ejecuta tu compra")
        col_bid, col_ask = st.columns(2)
        col_bid.metric("💰 BID (Compradores ofrecen)", "$99.50", delta_color="off")
        col_ask.metric("🏷️ ASK (Vendedores exigen)", "$100.50", delta_color="off")
        
        tipo_orden = st.radio(
            "Elige tu instrucción para el Bróker:", 
            ["A Mercado", "Limitada"],
            help="**A Mercado:** Priorizas comprar YA, sin importar el precio exacto.\n\n**Limitada:** Priorizas el PRECIO."
        )
        
        precio_limite = 0.0
        if tipo_orden == "Limitada":
            precio_limite = st.number_input("Precio máximo a pagar ($):", min_value=1.0, value=99.00, step=0.10)
            
        if st.button("🚀 Enviar Orden", type="primary"):
            if tipo_orden == "A Mercado":
                st.success("✅ **ORDEN EJECUTADA:** Compraste al instante por $100.50.")
            elif precio_limite >= 100.50:
                st.success(f"✅ **ORDEN EJECUTADA:** Ofreciste ${precio_limite:.2f}, pero se ejecutó al mejor precio disponible: $100.50.")
            else:
                st.warning(f"⏳ **ORDEN PENDIENTE:** Tu oferta de ${precio_limite:.2f} está a la espera en el libro de órdenes.")

    st.markdown("---")
    st.subheader("🏆 Evaluación Final: Reto de Simulación")
    with st.form("quiz_form"):
        q1 = st.radio("1. Noticia con Hype (100/100). ¿Qué haces?", 
                      ["a) Comprar usando Orden a Mercado.", "b) Evaluar riesgo (posible sobreestimación).", "c) Invertir todo en Cetes."])
        q2 = st.radio("2. Estás dispuesto a pagar un precio máximo. ¿Qué orden utilizas?", 
                      ["a) Orden a Mercado.", "b) Stop-loss.", "c) Orden Limitada."])
        
        enviado = st.form_submit_button("✅ Enviar Respuestas")
        if enviado:
            if q1.startswith("b") and q2.startswith("c"):
                st.success("🎉 **¡Felicidades!** Has respondido correctamente a las preguntas clave.")
            else:
                st.error("❌ Algunas respuestas son incorrectas. Revisa las lecciones.")

# --- ORQUESTADOR PRINCIPAL ---
def main() -> None:
    aplicar_estilos_css()
    inicializar_estado()
    
    with st.sidebar:
        st.title("FirstFolio 🔭")
        st.caption("Plataforma de Inteligencia Financiera")
        st.info("MVP con integración de IA Generativa y Análisis Estructural Cuantitativo.")
    
    tab1, tab2, tab3 = st.tabs(["🚀 Radar de Oportunidades (IA)", "🌍 Monitor de Riesgo (RVM)", "🎓 Aula Virtual"])
    
    with tab1: renderizar_tab_ia()
    with tab2: renderizar_tab_rvm()
    with tab3: renderizar_tab_aula()

if __name__ == "__main__":
    main()
