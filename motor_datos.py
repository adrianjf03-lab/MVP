
"""
motor_datos.py — Pipeline de Datos e IA para FirstFolio
========================================================
Responsabilidades:
  1. Descargar cotizaciones de mercado via yfinance (con caché).
  2. Buscar noticias relevantes via NewsAPI.
  3. Ejecutar el pipeline NLP asíncrono (NER + Análisis Amara) usando Groq/Llama-3.

Arquitectura de concurrencia:
  - asyncio.run() gestiona el ciclo de vida del Event Loop de forma segura.
  - asyncio.Semaphore controla la presión sobre la API de Groq (rate limits).
  - asyncio.to_thread() delega operaciones síncronas de I/O (yfinance) al threadpool,
    evitando bloquear el Event Loop principal.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any
import nest_asyncio
nest_asyncio.apply()
import groq as groq_sdk
import streamlit as st
import yfinance as yf
from groq import AsyncGroq
from newsapi import NewsApiClient

# ---------------------------------------------------------------------------
# Configuración de logging (reemplaza los print() sueltos)
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("firstfolio.motor")
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logging.getLogger("peewee").setLevel(logging.CRITICAL)

# ---------------------------------------------------------------------------
# Configuración de APIs (leídas desde Streamlit Secrets)
# ---------------------------------------------------------------------------
GROQ_API_KEY: str = st.secrets["GROQ_API_KEY"]
NEWS_API_KEY: str = st.secrets["NEWS_API_KEY"]

newsapi = NewsApiClient(api_key=NEWS_API_KEY)

# ---------------------------------------------------------------------------
# Constantes del pipeline
# ---------------------------------------------------------------------------
GROQ_MODEL = "llama-3.1-8b-instant"
GROQ_TIMEOUT_S = 45.0
GROQ_CONCURRENCY = 5       # Slots simultáneos sobre la API de Groq
NEWS_PAGE_SIZE = 12        # Artículos a solicitar; se filtran hasta ~4 válidos
NEWS_LOOKBACK_DAYS = 3
MAX_RESULTS = 4


# ===========================================================================
# MÓDULO 1: DATOS DE MERCADO
# ===========================================================================

@st.cache_data(ttl=300)  # Caché de 5 min: evita re-descargas del mismo ticker
def obtener_datos_accion(ticker: str, periodo: str = "5d") -> dict[str, Any] | None:
    """
    Descarga el historial de precios reciente para mostrar la cotización en vivo.

    Args:
        ticker: Símbolo bursátil (ej. "NVDA").
        periodo: Periodo de descarga para yfinance (default "5d" para mayor
                 fiabilidad con días de trading que "1mo").

    Returns:
        Diccionario con precio_actual y variacion_pct, o None si falla.
    """
    try:
        historial = yf.Ticker(ticker).history(period=periodo)
        if historial.empty or len(historial) < 2:
            return None

        precio_actual = float(historial["Close"].iloc[-1])
        precio_anterior = float(historial["Close"].iloc[-2])
        variacion = ((precio_actual - precio_anterior) / precio_anterior) * 100

        return {
            "precio_actual": round(precio_actual, 2),
            "variacion_pct": round(variacion, 2),
        }
    except Exception:
        logger.debug("No se pudo obtener datos para ticker '%s'.", ticker)
        return None


def _es_ticker_valido_sync(ticker: str) -> bool:
    """
    Validación síncrona de un ticker contra yfinance.
    Se llama via asyncio.to_thread() para no bloquear el Event Loop.

    Args:
        ticker: Símbolo bursátil a validar.

    Returns:
        True si el ticker tiene datos reales en el último día de trading.
    """
    if not ticker or ticker == "NONE" or not (1 <= len(ticker) <= 5):
        return False
    try:
        hist = yf.Ticker(ticker).history(period="5d")
        return not hist.empty
    except Exception:
        return False


# ===========================================================================
# MÓDULO 2: PIPELINE DE INTELIGENCIA ARTIFICIAL (Asíncrono)
# ===========================================================================

async def _extraer_ticker_ia(
    client: AsyncGroq,
    sem: asyncio.Semaphore,
    titulo: str,
    descripcion: str,
) -> str:
    """
    Paso 1 del pipeline: NER (Named Entity Recognition) para extraer el ticker
    de la empresa principal afectada por la noticia.

    Usa temperatura 0.0 para máximo determinismo. Max 10 tokens para forzar
    la respuesta más corta posible.

    Args:
        client: Cliente asíncrono de Groq.
        sem: Semáforo de concurrencia.
        titulo: Titular de la noticia.
        descripcion: Cuerpo o resumen de la noticia.

    Returns:
        Ticker en mayúsculas (ej. "NVDA") o "NONE" si no hay empresa cotizada.
    """
    system_msg = (
        "You are a financial NER parser. "
        "You output ONLY the requested data — no explanations, no punctuation."
    )
    user_msg = (
        f"News: {titulo} — {descripcion}\n\n"
        "Task: Extract the PRIMARY US stock ticker (NASDAQ/NYSE) of the company "
        "most directly affected by this news.\n"
        "Rules:\n"
        "- Output ONLY the ticker (1-5 uppercase letters). E.g.: AAPL, NVDA, MSFT\n"
        "- If the news covers a broad sector, commodity, crypto, index, or no specific "
        "listed company → output exactly: NONE\n"
        "- If multiple companies appear, pick the ONE most central to the story.\n"
        "- NEVER add spaces, punctuation, or any other text."
    )

    async with sem:
        for attempt in range(3):
            try:
                res = await client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": user_msg},
                    ],
                    model=GROQ_MODEL,
                    temperature=0.0,
                    max_tokens=10,
                )
                raw = res.choices[0].message.content.strip().upper()
                # Limpieza defensiva: eliminar caracteres no alfanuméricos
                ticker = "".join(c for c in raw if c.isalpha())
                return ticker if 1 <= len(ticker) <= 5 else "NONE"

            except groq_sdk.RateLimitError:
                wait = (attempt + 1) * 3  # Backoff exponencial: 3s, 6s, 9s
                logger.warning("Rate limit en extraer_ticker. Esperando %ds...", wait)
                await asyncio.sleep(wait)
            except groq_sdk.APITimeoutError:
                logger.warning("Timeout en extraer_ticker (intento %d).", attempt + 1)
                await asyncio.sleep(1)
            except Exception as e:
                logger.error("Error inesperado en extraer_ticker: %s", e)
                await asyncio.sleep(1)

    return "NONE"


async def _analizar_amara_ia(
    client: AsyncGroq,
    sem: asyncio.Semaphore,
    ticker: str,
    titulo: str,
    descripcion: str,
) -> dict[str, Any] | None:
    """
    Paso 2 del pipeline: Análisis cuantitativo de Hype (Ley de Amara) y sentimiento.

    El system message separa el ROL del modelo de los DATOS de la noticia,
    lo que mejora la adherencia a instrucciones en modelos Llama-3.

    Args:
        client: Cliente asíncrono de Groq.
        sem: Semáforo de concurrencia.
        ticker: Símbolo del activo ya validado.
        titulo: Titular de la noticia.
        descripcion: Resumen de la noticia.

    Returns:
        Diccionario con sentimiento, nivel_hype, fase_amara y razon; o None si falla.
    """
    system_msg = (
        "You are the Chief Quantitative Analyst at a global macro hedge fund. "
        "You are brutally skeptical of corporate marketing and media hype. "
        "You always respond with ONLY valid JSON — no markdown, no preamble."
    )

    # Anclas de calibración para reducir la tendencia del modelo a concentrarse en valores medios
    calibration_examples = (
        "Calibration anchors for nivel_hype:\n"
        "- NVDA during peak AI frenzy (Feb 2024 'AI will replace everything' headlines) → 95\n"
        "- TSLA after viral Elon tweet with no product update → 88\n"
        "- Boring patent filing for battery chemistry improvement → 15\n"
        "- Regulatory approval for generic drug (no branding) → 12\n"
        "- Solid earnings beat with raised guidance → 45\n"
    )

    user_msg = (
        f"Analyze this news about {ticker}:\n"
        f'"{titulo} — {descripcion}"\n\n'
        "Apply Amara's Law: humans overestimate tech impact short-term, underestimate long-term.\n\n"
        "Hype scoring guide:\n"
        "- 70–100: Bubble / FOMO. Buzzwords (revolutionary, AI, game-changer) without hard metrics or timeline. Short-term overestimation.\n"
        "- 40–69: Balanced coverage with verifiable near-term claims.\n"
        "- 0–39: Boring structural development (capex, patents, regulatory). Long-term underestimation.\n\n"
        f"{calibration_examples}\n"
        "Return ONLY this JSON object:\n"
        "{\n"
        '  "sentimiento": "Positivo" | "Negativo" | "Neutro",\n'
        '  "nivel_hype": <integer 0-100>,\n'
        '  "fase_amara": "Sobreestimación a Corto Plazo" | "Subestimación a Largo Plazo" | '
        '"Expectativas Equilibradas" | "Ruido Irrelevante",\n'
        '  "razon": "<one sentence in Spanish, max 20 words, cynically honest>"\n'
        "}"
    )

    async with sem:
        for attempt in range(3):
            try:
                res = await client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": user_msg},
                    ],
                    model=GROQ_MODEL,
                    temperature=0.1,
                    max_tokens=250,
                    response_format={"type": "json_object"},
                )
                return _parse_json_safe(res.choices[0].message.content)

            except groq_sdk.RateLimitError:
                wait = (attempt + 1) * 3
                logger.warning("Rate limit en analizar_amara. Esperando %ds...", wait)
                await asyncio.sleep(wait)
            except groq_sdk.APITimeoutError:
                logger.warning("Timeout en analizar_amara (intento %d).", attempt + 1)
                await asyncio.sleep(1)
            except Exception as e:
                logger.error("Error inesperado en analizar_amara: %s", e)
                await asyncio.sleep(1)

    return None


def _parse_json_safe(raw: str) -> dict[str, Any] | None:
    """
    Parser de JSON robusto: elimina fences de markdown y whitespace
    antes de intentar el parse. Nunca lanza excepción.

    Args:
        raw: String de respuesta del LLM.

    Returns:
        Diccionario parseado o None si el contenido no es JSON válido.
    """
    import json
    import re

    # Eliminar posibles fences ```json ... ``` que el modelo añade a veces
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning("JSON parse falló: %s | Raw: %.100s...", e, raw)
        return None


async def _procesar_noticia(
    articulo: dict[str, Any],
    client: AsyncGroq,
    sem: asyncio.Semaphore,
) -> dict[str, Any] | None:
    """
    Pipeline completo para una sola noticia:
      1. Extracción del ticker (NER)
      2. Validación del ticker contra yfinance (en hilo síncrono)
      3. Análisis de Hype y sentimiento (Amara)

    Nota: Los pasos 1 y 2 son "baratos" (pocas tokens, I/O rápido).
    Solo se ejecuta el paso 3 (costoso en tokens) si el ticker existe.

    Args:
        articulo: Diccionario con datos del artículo de NewsAPI.
        client: Cliente asíncrono de Groq.
        sem: Semáforo de concurrencia.

    Returns:
        Diccionario con el análisis completo, o None si se filtra en algún paso.
    """
    titulo = articulo.get("title", "")
    descripcion = articulo.get("description") or articulo.get("content", "")
    if not descripcion:
        return None

    # Paso 1: Extracción NER
    ticker = await _extraer_ticker_ia(client, sem, titulo, descripcion)
    if ticker == "NONE":
        return None

    # Paso 2: Validación (I/O síncrono en threadpool)
    es_real = await asyncio.to_thread(_es_ticker_valido_sync, ticker)
    if not es_real:
        logger.debug("Ticker '%s' no validado por yfinance — descartando.", ticker)
        return None

    # Paso 3: Análisis profundo (solo si el ticker es real)
    analisis = await _analizar_amara_ia(client, sem, ticker, titulo, descripcion)
    if not analisis:
        return None

    return {
        "titulo": titulo,
        "fuente": articulo.get("source", {}).get("name", "Desconocida"),
        "ticker_relacionado": ticker,
        "ia_sentimiento": analisis.get("sentimiento", "Neutro"),
        "ia_hype": analisis.get("nivel_hype", 50),
        "ia_fase": analisis.get("fase_amara", "Expectativas Equilibradas"),
        "ia_razon": analisis.get("razon", "Sin análisis disponible."),
    }


async def _flujo_principal_async(
    articulos: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Cerebro de concurrencia: instancia el cliente y el semáforo dentro del
    Event Loop activo y procesa todos los artículos en paralelo.

    Args:
        articulos: Lista de artículos crudos de NewsAPI.

    Returns:
        Lista filtrada de noticias con análisis completo.
    """
    # El cliente se instancia DENTRO del loop para evitar problemas con el
    # event loop de httpx subyacente en múltiples ejecuciones.
    client = AsyncGroq(api_key=GROQ_API_KEY, timeout=GROQ_TIMEOUT_S)
    sem = asyncio.Semaphore(GROQ_CONCURRENCY)

    tareas = [_procesar_noticia(art, client, sem) for art in articulos]
    # return_exceptions=True: si falla una noticia, no cancela las demás
    resultados = await asyncio.gather(*tareas, return_exceptions=True)

    validos = [r for r in resultados if isinstance(r, dict)]
    logger.info(
        "Pipeline completado: %d/%d artículos procesados con éxito.",
        len(validos),
        len(articulos),
    )
    return validos


# ===========================================================================
# PUNTO DE ENTRADA PÚBLICO (llamado por Streamlit de forma síncrona)
# ===========================================================================

def obtener_noticias_ia(tema_busqueda: str) -> list[dict[str, Any]]:
    """
    Punto de entrada síncrono para el pipeline de noticias + IA.
    Llamado directamente desde app.py (contexto síncrono de Streamlit).

    Flujo:
      1. Descarga N artículos de NewsAPI.
      2. Lanza el pipeline asíncrono (NER + Amara) sobre todos.
      3. Devuelve los primeros MAX_RESULTS resultados válidos.

    Args:
        tema_busqueda: Término de búsqueda en inglés (ej. "Artificial Intelligence").

    Returns:
        Lista de diccionarios con los análisis, limitada a MAX_RESULTS.
    """
    logger.info("Iniciando búsqueda de noticias para: '%s'", tema_busqueda)

    fecha_desde = (datetime.now() - timedelta(days=NEWS_LOOKBACK_DAYS)).strftime(
        "%Y-%m-%d"
    )

    try:
        respuesta = newsapi.get_everything(
            q=tema_busqueda,
            from_param=fecha_desde,
            language="en",
            sort_by="relevancy",
            page_size=NEWS_PAGE_SIZE,
        )
        articulos = respuesta.get("articles", [])
        logger.info("NewsAPI devolvió %d artículos.", len(articulos))
    except Exception as e:
        logger.error("Error al consultar NewsAPI: %s", e)
        return []

    if not articulos:
        return []

    try:
        # asyncio.run() crea un nuevo Event Loop limpio, ejecuta la corutina
        # y lo destruye — es el patrón estándar desde Python 3.7.
        noticias_validas = asyncio.run(_flujo_principal_async(articulos))
    except Exception as e:
        logger.error("Error crítico en el pipeline asíncrono: %s", e)
        return []

    return noticias_validas[:MAX_RESULTS]
