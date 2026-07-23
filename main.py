# -*- coding: utf-8 -*-
import os
import asyncio
import logging
from contextlib import asynccontextmanager
from urllib.parse import quote, unquote, urljoin

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, Response, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("iptv-ultra-proxy")

# ---------------------------------------------------------------------
# Configuración de Entorno
# ---------------------------------------------------------------------
ARCHIVO_M3U = os.environ.get(
    "M3U_PATH", os.path.join(os.path.dirname(__file__), "lista.m3u")
)

# Forzar HTTPS si estás en Render (Evita bucles o errores de esquema HTTP)
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")

# Tiempos de espera y reutilización de conexiones TCP
TIMEOUTS = httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=10.0)
LIMITS = httpx.Limits(max_keepalive_connections=50, max_connections=100)

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Connection": "keep-alive",
}

# Lifecycle moderno de FastAPI
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = httpx.AsyncClient(
        timeout=TIMEOUTS,
        limits=LIMITS,
        headers=DEFAULT_HEADERS,
        follow_redirects=True,
    )
    yield
    await app.state.http_client.aclose()

app = FastAPI(title="IPTV Engine - Zero Buffer Proxy", lifespan=lifespan)

# Compresión Gzip para la lista M3U
app.add_middleware(GZipMiddleware, minimum_size=256)

# CORS Abierto
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------
# Funciones Auxiliares
# ---------------------------------------------------------------------
def base_url_de(request: Request) -> str:
    if PUBLIC_BASE_URL:
        return PUBLIC_BASE_URL
    return str(request.base_url).rstrip("/")

def parsear_linea_canal(linea_str: str):
    """Soporta enlaces tipo 'url|Header1=valor&Header2=valor'."""
    if "|" not in linea_str:
        return linea_str, {}

    url_real, extra = linea_str.split("|", 1)
    headers = {}
    for par in extra.split("&"):
        if "=" in par:
            k, v = par.split("=", 1)
            headers[k.strip()] = v.strip()
    return url_real, headers

def construir_url_proxy(base_url: str, url_real: str, headers: dict) -> str:
    partes = [f"url={quote(url_real, safe='')}"]
    for k, v in headers.items():
        partes.append(f"h_{quote(k, safe='')}={quote(v, safe='')}")
    return f"{base_url}/stream?{'&'.join(partes)}"

def extraer_headers_extra(request: Request) -> dict:
    """Extrae parámetros de cabecera 'h_Nombre=Valor'."""
    headers = {}
    for k, values in request.query_params.multi_items():
        if k.startswith("h_"):
            headers[k[2:]] = values
    return headers

def es_playlist_hls(content_type: str, url: str) -> bool:
    ct = (content_type or "").lower()
    return "mpegurl" in ct or url.lower().split("?")[0].endswith(".m3u8")

async def reescribir_m3u8(texto: str, url_origen: str, base_url: str, headers_canal: dict) -> str:
    """Reescribe listas HLS internamente para mantener la protección en los segmentos .ts."""
    lineas_out = []
    for linea in texto.splitlines():
        linea_limpia = linea.strip()
        if linea_limpia and not linea_limpia.startswith("#"):
            url_absoluta = urljoin(url_origen, linea_limpia)
            lineas_out.append(construir_url_proxy(base_url, url_absoluta, headers_canal))
        else:
            lineas_out.append(linea)
    return "\n".join(lineas_out)

# ---------------------------------------------------------------------
# 1. GENERADOR DINÁMICO DE M3U
# ---------------------------------------------------------------------
@app.get("/playlist.m3u")
@app.get("/lista.m3u")
async def obtener_playlist(request: Request):
    if not os.path.exists(ARCHIVO_M3U):
        raise HTTPException(status_code=404, detail="Archivo lista.m3u no encontrado en el servidor")

    base_url = base_url_de(request)

    with open(ARCHIVO_M3U, "r", encoding="utf-8", errors="ignore") as f:
        lineas = f.readlines()

    nueva_lista = [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        "#EXT-X-ALLOW-CACHE:YES"
    ]

    for linea in lineas:
        linea_str = linea.strip()
        if not linea_str:
            continue

        if linea_str.startswith("http://") or linea_str.startswith("https://") or "|" in linea_str:
            url_real, headers = parsear_linea_canal(linea_str)
            nueva_lista.append(construir_url_proxy(base_url, url_real, headers))
        else:
            nueva_lista.append(linea_str)

    contenido_m3u = "\n".join(nueva_lista)
    return Response(content=contenido_m3u, media_type="application/vnd.apple.mpegurl")

# ---------------------------------------------------------------------
# 2. MOTOR ANTI-BUFFERING Y STREAMING DIRECTO
# ---------------------------------------------------------------------
async def flujo_video_anti_buffer(target_url: str, client: httpx.AsyncClient, headers: dict, rango: str | None):
    """
    Descarga el flujo desde el proveedor lejanos, absorbe micro-cortes de red
    y retransmite en bloques limpios de 64KB hacia la TV.
    """
    retry_count = 0
    max_retries = 3
    req_headers = dict(headers)
    if rango:
        req_headers["Range"] = rango

    while retry_count < max_retries:
        try:
            async with client.stream("GET", target_url, headers=req_headers) as response:
                if response.status_code not in (200, 206):
                    logger.warning(f"Estado inusual del proveedor: {response.status_code}")
                    retry_count += 1
                    await asyncio.sleep(0.5)
                    continue

                # Buffer en memoria RAM enviando paquetes continuos de 64KB
                async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                    if chunk:
                        yield chunk
                return

        except (httpx.TransportError, httpx.TimeoutException) as err:
            logger.error(f"Error de red absorbido en Render: {err}. Reconectando...")
            retry_count += 1
            await asyncio.sleep(0.5)

    logger.error(f"Conexión perdida permanentemente para: {target_url}")

@app.get("/stream")
async def proxy_stream(url: str, request: Request):
    """Endpoint principal de retransmisión."""
    if not url:
        raise HTTPException(status_code=400, detail="Parámetro 'url' requerido")

    url_real = unquote(url)
    headers_canal = extraer_headers_extra(request)
    client: httpx.AsyncClient = request.app.state.http_client
    rango = request.headers.get("range")

    # OPTIMIZACIÓN ZAPPING: Si es un canal en directo .ts, saltamos la inspección e iniciamos stream inmediato
    url_limpia = url_real.split("?")[0].lower()
    if url_limpia.endswith(".ts"):
        return StreamingResponse(
            flujo_video_anti_buffer(url_real, client, headers_canal, rango),
            media_type="video/mp2t",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
                "Access-Control-Allow-Origin": "*",
                "X-Accel-Buffering": "no",
            },
        )

    # Si es un manifest HLS (.m3u8) o stream no identificado, lo procesamos
    try:
        req_headers = dict(headers_canal)
        if rango:
            req_headers["Range"] = rango
        async with client.stream("GET", url_real, headers=req_headers) as resp:
            content_type = resp.headers.get("content-type", "")

            if es_playlist_hls(content_type, url_real):
                cuerpo = (await resp.aread()).decode("utf-8", errors="ignore")
                base_url = base_url_de(request)
                reescrito = await reescribir_m3u8(cuerpo, url_real, base_url, headers_canal)
                return PlainTextResponse(
                    reescrito,
                    media_type="application/vnd.apple.mpegurl",
                    headers={
                        "Cache-Control": "no-cache, no-store, must-revalidate",
                        "Access-Control-Allow-Origin": "*",
                    },
                )
    except (httpx.TransportError, httpx.TimeoutException) as err:
        raise HTTPException(status_code=502, detail=f"Error al contactar con el origen del canal: {err}")

    # Fallback para streams binarios
    return StreamingResponse(
        flujo_video_anti_buffer(url_real, client, headers_canal, rango),
        media_type="video/mp2t",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "Access-Control-Allow-Origin": "*",
            "X-Accel-Buffering": "no",
        },
    )
