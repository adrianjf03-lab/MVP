
import asyncio
import yfinance as yf
from newsapi import NewsApiClient
from groq import AsyncGroq
import json
import logging
import re
from datetime import datetime, timedelta
import streamlit as st
from typing import Optional, Dict, List

# --- CONFIGURACIÓN DEL ENTORNO ---
yf.set_tz_cache_location("cache") 
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

try:
    GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
    NEWS_API_KEY = st.secrets["NEWS_API_KEY"]
except KeyError as e:
    st.error(f"Falta configurar la variable de entorno: {e}")
    st.stop()

newsapi = NewsApiClient(api_key=NEWS_API_KEY)

# --- UTILIDADES ROBUSTAS ---

def extraer_json_seguro(respuesta_llm: str) -> dict:
    """Extrae JSON de manera robusta eliminando artefactos Markdown del LLM."""
    try:
        match = re.search(r'\{.*\}', respuesta_llm, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return {}
    except json.JSONDecodeError:
        logging.error(f"Fallo al decodificar JSON del LLM: {respuesta_llm}")
        return {}

# --- MÓDULO 1: DATOS DE MERCADO ---

@st.cache_data(ttl=300) 
def obtener_datos_accion(ticker: str, periodo: str = "1mo") -> Optional[Dict[str, float]]:
    """Descarga el historial de precios para la UI de Streamlit de forma síncrona."""
    try:
        t = yf.Ticker(ticker)
        historial = t.history(period=periodo)
        if historial.empty or len(historial) < 2: 
            return None
        
        precio_actual = historial['Close'].iloc[-1]
        precio_ayer = historial['Close'].iloc[-2]
        variacion = ((precio_actual - precio_ayer) / precio_ayer) * 100
        
        return {
            "precio_actual": round(precio_actual, 2),
            "variacion_pct": round(variacion, 2)
        }
    except Exception as e:
        logging.warning(f"Error al obtener precios para {ticker}: {e}")
        return None
        
def es_ticker_valido(ticker: str) -> bool:
    """Validación rápida delegada a un hilo aparte para no bloquear asyncio."""
    if not ticker or ticker == "NONE" or len(ticker) > 5:
        return False
    try:
        return 'symbol' in yf.Ticker(ticker).fast_info
    except Exception:
        return False

# --- MÓDULO 2: INTELIGENCIA ARTIFICIAL (ROBUSTA Y ENCAPSULADA) ---

async def extraer_ticker_ia(client: AsyncGroq, sem: asyncio.Semaphore, titulo: str, descripcion: str) -> str:
    """Paso 1: NER (Reconocimiento de Entidades) con prevención de alucinaciones."""
    prompt = f"""
    Actúa como un sistema de Extracción de Entidades Financieras (NER) de alta precisión.
    Analiza el siguiente titular y descripción: "{titulo} - {descripcion}"

    TAREA: Extrae ÚNICAMENTE el Ticker oficial (símbolo bursátil) de la empresa pública americana (NASDAQ/NYSE) que sea el SUJETO PRINCIPAL de la noticia.

    REGLAS ESTRICTAS:
    1. Si la noticia trata sobre una empresa PRIVADA (ej. OpenAI, xAI, Stripe, SpaceX), responde EXACTAMENTE: NONE.
    2. Si se mencionan varias empresas públicas, elige SOLO la que recibe el impacto directo del evento narrado.
    3. Si es un artículo genérico sobre sectores o macroeconomía, responde EXACTAMENTE: NONE.
    4. Tu respuesta no debe contener NINGÚN carácter adicional, ni puntuación, ni explicaciones. SOLO el Ticker (ej. AAPL) o NONE.
    """
    
    async with sem: 
        for intento in range(3):
            try:
                res = await client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model="llama-3.1-8b-instant",
                    temperature=0.0,
                    max_tokens=15
                )
                texto = res.choices[0].message.content.strip().upper()
                ticker = re.sub(r'[^A-Z]', '', texto) 
                return ticker if 1 <= len(ticker) <= 5 else "NONE"
            except Exception as e:
                logging.warning(f"Intento {intento+1} fallido NER: {e}")
                await asyncio.sleep((intento + 1) * 2) 
        return "NONE"

async def analizar_amara_ia(client: AsyncGroq, sem: asyncio.Semaphore, ticker: str, titulo: str, descripcion: str) -> Optional[Dict]:
    """Paso 2: Prompt Avanzado - Analista Hedge Fund con enfoque en Catalizadores."""
    prompt = f"""
    Actúa como el Analista Cuantitativo Jefe de un Hedge Fund de Nueva York. Eres analítico, escéptico ante las narrativas corporativas y experto en detectar burbujas mediáticas.
    Analiza esta noticia sobre el ticker {ticker}: "{titulo} - {descripcion}"

    Aplica el marco mental de la 'Ley de Amara' (sobreestimamos el impacto a corto plazo de una tecnología y subestimamos el de largo plazo):
    - Hype Alto (70-100): Exceso de optimismo, FOMO mediático, promesas sin tracción comercial actual (Riesgo de sobreestimación a corto plazo).
    - Hype Bajo (0-40): Desarrollos estructurales aburridos pero vitales, patentes, infraestructura, ventajas competitivas silenciosas (Oportunidad a largo plazo).

    Devuelve ÚNICAMENTE un objeto JSON válido con esta estructura exacta:
    {{
        "sentimiento": "Positivo" | "Negativo" | "Neutro",
        "nivel_hype": <int de 0 a 100>,
        "fase_amara": "Burbuja de Expectativas" | "Consolidación Silenciosa" | "Ruido Irrelevante" | "Adopción Real",
        "catalizador_real": "<Identifica en máximo 10 palabras qué mueve realmente el precio aquí, ignorando el marketing>",
        "razon": "<Tu tesis analítica, directa y profesional en máximo 25 palabras>"
    }}
    """
    
    async with sem:
        for intento in range(3):
            try:
                res = await client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model="llama-3.1-8b-instant",
                    temperature=0.1, 
                    max_tokens=250,
                    response_format={"type": "json_object"} 
                )
                raw_content = res.choices[0].message.content
                return extraer_json_seguro(raw_content)
            except Exception as e:
                logging.warning(f"Intento {intento+1} fallido Análisis: {e}")
                await asyncio.sleep((intento + 1) * 2)
        return None

async def procesar_noticia(articulo: dict, client: AsyncGroq, sem: asyncio.Semaphore) -> Optional[Dict]:
    """Pipeline completo de una sola noticia (NER -> Validar -> Analizar)."""
    descripcion = articulo.get('description', '')
    if not descripcion: 
        return None

    ticker = await extraer_ticker_ia(client, sem, articulo['title'], descripcion)
    if ticker == "NONE": return None

    es_real = await asyncio.to_thread(es_ticker_valido, ticker)
    if not es_real: return None

    analisis = await analizar_amara_ia(client, sem, ticker, articulo['title'], descripcion)
    if not analisis: return None
    
    return {
        "titulo": articulo['title'],
        "fuente": articulo['source']['name'],
        "ticker_relacionado": ticker,
        "ia_sentimiento": analisis.get('sentimiento', 'Neutro'),
        "ia_hype": int(analisis.get('nivel_hype', 50)),
        "ia_fase": analisis.get('fase_amara', 'Desconocida'),
        "ia_catalizador": analisis.get('catalizador_real', 'No detectado'),
        "ia_razon": analisis.get('razon', 'Sin análisis detallado')
    }

async def flujo_principal_async(articulos: List[dict]) -> List[dict]:
    """Cerebro de Concurrencia que administra el pool de peticiones."""
    client = AsyncGroq(api_key=GROQ_API_KEY, timeout=30.0)
    sem = asyncio.Semaphore(8) 
    
    tareas = [procesar_noticia(art, client, sem) for art in articulos]
    resultados = await asyncio.gather(*tareas, return_exceptions=True)
    
    return [r for r in resultados if isinstance(r, dict)]

def obtener_noticias_ia(tema_busqueda: str) -> List[dict]:
    """Punto de entrada orquestador llamado por la UI."""
    fecha_desde = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')
    
    try:
        req = newsapi.get_everything(
            q=tema_busqueda, 
            from_param=fecha_desde, 
            language='en', 
            sort_by='relevancy', 
            page_size=40 
        )
        articulos = req.get('articles', [])
    except Exception as e:
        logging.error(f"Error conectando a NewsAPI: {e}")
        return []

    try:
        noticias_validas = asyncio.run(flujo_principal_async(articulos))
        return noticias_validas[:4]
    except Exception as e:
        logging.error(f"Error Crítico en el Event Loop Async: {e}")
        return []
