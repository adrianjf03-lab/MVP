# FirstFolio MVP

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://firstfoliomvp.streamlit.app/)

**FirstFolio** es una plataforma web hibrida de analitica financiera y educacion para inversores minoristas. Su objetivo es reducir la asimetria de informacion y ayudar al usuario a tomar decisiones mas disciplinadas frente al ruido mediatico, la euforia de mercado y los sesgos cognitivos.

**App en produccion:** [https://firstfoliomvp.streamlit.app/](https://firstfoliomvp.streamlit.app/)

## Descripcion

El MVP combina inteligencia artificial generativa, analisis cuantitativo macro-financiero y simuladores educativos. La aplicacion esta desarrollada con **Streamlit** y organiza la experiencia en tres modulos principales:

1. **Radar de Oportunidades con IA**
   - Ingesta noticias recientes mediante NewsAPI.
   - Extrae entidades financieras y tickers de empresas cotizadas.
   - Analiza sentimiento, nivel de Hype y fase de la Ley de Amara usando Groq/Llama.
   - Ayuda a distinguir entre noticias con valor informativo y narrativas de FOMO.

2. **Monitor de Riesgo Macro-Financiero (RVM)**
   - Calcula un Indice de Vulnerabilidad (IV Score) para divisas seleccionadas.
   - Usa retornos logaritmicos, downside volatility, devaluacion anual y normalizacion Z-Score.
   - Visualiza el riesgo mediante mapa geografico y radar regional con Plotly.

3. **Aula Virtual**
   - Explica conceptos basicos de inversion para usuarios sin experiencia.
   - Ensena a interpretar el Radar IA y el Monitor RVM.
   - Incluye simuladores de inflacion, diversificacion, tipos de orden y tamano de posicion.
   - Integra un checklist educativo antes de tomar decisiones de inversion.

## Arquitectura

```text
FirstFolio
|-- app.py              # Interfaz Streamlit y orquestacion de pestanas
|-- motor_datos.py      # Pipeline de noticias, datos de mercado e IA
|-- rvm_logic.py        # Calculo cuantitativo del Radar de Vulnerabilidad Macro
|-- requirements.txt    # Dependencias del proyecto
`-- .streamlit/
    `-- secrets.toml.example
```

## Stack tecnico

- Python
- Streamlit
- Pandas / NumPy
- Plotly
- SciPy
- yfinance
- NewsAPI
- Groq API / Llama

## Instalacion local

Clona el repositorio:

```bash
git clone https://github.com/tu-usuario/firstfolio-mvp.git
cd firstfolio-mvp
```

Crea un entorno virtual:

```bash
python -m venv .venv
```

Activa el entorno:

```bash
# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

Instala dependencias:

```bash
pip install -r requirements.txt
```

## Variables de entorno

La aplicacion requiere claves externas para el radar de noticias e IA.

Crea un archivo `.streamlit/secrets.toml` tomando como referencia:

```toml
GROQ_API_KEY = "tu_clave_de_groq"
NEWS_API_KEY = "tu_clave_de_newsapi"
```

Tambien puedes usar el archivo incluido:

```text
.streamlit/secrets.toml.example
```

## Ejecucion

```bash
streamlit run app.py
```

La aplicacion se abrira normalmente en:

```text
http://localhost:8501
```

## Formula del IV Score

El Radar de Vulnerabilidad Macro calcula el indice final mediante una combinacion ponderada:

```text
IV = 0.30*Comp_Asim_Abs
   + 0.10*Comp_Asim_Rel
   + 0.10*Comp_Hist_Z
   + 0.30*Comp_Vol_Total
   + 0.20*Comp_Deval
```

Donde:

- `Comp_Asim_Abs`: volatilidad asimetrica normalizada.
- `Comp_Asim_Rel`: ranking percentil de volatilidad asimetrica.
- `Comp_Hist_Z`: Z-Score de estres reciente.
- `Comp_Vol_Total`: volatilidad historica total.
- `Comp_Deval`: devaluacion anual normalizada.

## Objetivo academico

FirstFolio nace como un MVP academico-tecnico para explorar como una interfaz educativa puede combinar:

- analisis cuantitativo,
- inteligencia artificial generativa,
- visualizacion interactiva,
- educacion financiera,
- prevencion de sesgos conductuales.

El proyecto no busca sustituir el analisis financiero profesional, sino ofrecer una herramienta de aprendizaje y apoyo a la toma de decisiones.

## Aviso importante

Este proyecto tiene fines **educativos e informativos**. No constituye asesoramiento financiero, recomendacion de inversion ni oferta de compra o venta de instrumentos financieros. Toda decision de inversion debe considerar el perfil de riesgo, horizonte temporal, situacion financiera personal y, cuando sea necesario, la consulta con un profesional cualificado.

## App desplegada

Puedes probar el MVP aqui:

[https://firstfoliomvp.streamlit.app/](https://firstfoliomvp.streamlit.app/)
