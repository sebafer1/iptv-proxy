# -*- coding: utf-8 -*-
"""
Servidor de lista IPTV (M3U) - Versión optimizada para producción / Render.com

Mejoras respecto a la versión original:
  - FastAPI + Uvicorn (async): soporta cientos de conexiones simultáneas.
  - Compresión Gzip automática -> respuesta ultra rápida en Smart TVs y redes móviles.
  - Caché inteligente en RAM con refresco en background (cero esperas en la TV).
  - Tolerancia a fallos: si falla la descarga, sigue sirviendo la caché previa en RAM.
  - Seguridad integrada por Token para evitar que terceros accedan a tu lista.
"""

import os
import time
import asyncio
import logging
import urllib.request
from collections import defaultdict

from fastapi import FastAPI, Request, Query
from fastapi.responses import Response, PlainTextResponse
from fastapi.middleware.gzip import GZipMiddleware

# ------------------------------------------------------------------
# Configuración
# ------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("iptv")

# URL real de tu Pastebin
PASTEBIN_URL = "https://pastebin.com/raw/Q5V2s2Rd"

# Tu token de seguridad personalizado (puedes cambiarlo por el que quieras)
TOKEN_SEGURIDAD = "sangre123"

CACHE_TTL = 600          # Refrescar el origen cada 10 minutos (600 segundos)
REFRESH_INTERVAL = 30    # Frecuencia de revisión del estado de la caché (segundos)

# Rate limiting simple por IP
RATE_LIMIT_MAX = 20
RATE_LIMIT_WINDOW = 10   # segundos

# Cabeceras y metadatos válidos para no perder nombres ni logos
LINEAS_VALIDAS = (
    "http://", "https://",
    "#EXTM3U", "#EXTINF",
    "#EXTGRP", "#EXTVLCOPT",
    "#EXT-X-",
)

# ------------------------------------------------------------------
# Estado en memoria (Caché + Rate Limit)
# ------------------------------------------------------------------
CACHE_DATA: bytes | None = None
CACHE_TIMESTAMP: float = 0.0
CACHE_LOCK = asyncio.Lock()

_rate_hits: dict[str, list[float]] = defaultdict(list)


def _descargar_y_procesar_sync() -> bytes:
    """Descarga y limpia la lista M3U sin bloquear el flujo principal."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (SmartHub; SMART-TV; Windows NT 10.0; WOW64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) TV Safari/537.36"
        )
    }
    req = urllib.request.Request(PASTEBIN_URL, headers=headers)
    with urllib.request.urlopen(req, timeout=8) as response:
        contenido = response.read().decode("utf-8", errors="ignore")

    lista_limpia = []
    lineas = contenido.splitlines()
    
    # Asegurar cabecera obligatoria
    lista_limpia.append("#EXTM3U")
    
    i = 0
    while i < len(lineas):
        linea = lineas[i].strip()
        
        # Si es la metadata del canal (#EXTINF), verificamos que la línea siguiente sea el link
        if linea.startswith("#EXTINF"):
            if i + 1 < len(lineas) and lineas[i+1].strip().startswith(("http://", "https://")):
                lista_limpia.append(linea)                      # Agrega nombre/logo/grupo
                lista_limpia.append(lineas[i+1].strip())       # Agrega enlace de transmisión
                i += 2
                continue
        i += 1

    resultado = "\n".join(lista_limpia)
    return resultado.encode("utf-8")


async def refrescar_cache(forzar: bool = False):
    global CACHE_DATA, CACHE_TIMESTAMP

    ahora = time.time()
    if not forzar and CACHE_DATA is not None and (ahora - CACHE_TIMESTAMP) <= CACHE_TTL:
        return

    async with CACHE_LOCK:
        ahora = time.time()
        if not forzar and CACHE_DATA is not None and (ahora - CACHE_TIMESTAMP) <= CACHE_TTL:
            return

        try:
            nuevo = await asyncio.to_thread(_descargar_y_procesar_sync)
            CACHE_DATA = nuevo
            CACHE_TIMESTAMP = time.time()
            log.info("Caché actualizada en RAM de forma exitosa.")
        except Exception as e:
            if CACHE_DATA is not None:
                log.warning("Fallo al refrescar origen. Sirviendo copia previa en caché: %s", e)
            else:
                log.error("Fallo crítico: No hay caché previa y el origen falló: %s", e)


async def hilo_refresco_background():
    """Mantiene la caché fresca en segundo plano."""
    while True:
        await refrescar_cache()
        await asyncio.sleep(REFRESH_INTERVAL)


def rate_limit_ok(ip: str) -> bool:
    """Evita abusos de peticiones repetidas."""
    ahora = time.time()
    hits = _rate_hits[ip]
    while hits and ahora - hits[0] > RATE_LIMIT_WINDOW:
        hits.pop(0)
    if len(hits) >= RATE_LIMIT_MAX:
        return False
    hits.append(ahora)
    return True


# ------------------------------------------------------------------
# App FastAPI
# ------------------------------------------------------------------
app = FastAPI()
app.add_middleware(GZipMiddleware, minimum_size=500)


@app.on_event("startup")
async def startup():
    await refrescar_cache(forzar=True)
    asyncio.create_task(hilo_refresco_background())
    log.info("Servidor IPTV Iniciado. Listo para recibir conexiones.")


@app.get("/playlist")
@app.get("/playlist.m3u")
async def playlist(request: Request, token: str = Query(None, description="Token de acceso seguro")):
    # 1. Validación de seguridad obligatoria por Token
    if token != TOKEN_SEGURIDAD:
        return PlainTextResponse("Acceso denegado: Token inválido o no proporcionado.", status_code=403)

    # 2. Rate Limiting por IP
    ip = request.client.host if request.client else "desconocido"
    if not rate_limit_ok(ip):
        return PlainTextResponse("Demasiadas solicitudes. Intente en unos segundos.", status_code=429)

    # 3. Respuesta desde memoria RAM
    if CACHE_DATA is None:
        await refrescar_cache(forzar=True)

    if CACHE_DATA is None:
        return PlainTextResponse("Servicio temporalmente no disponible.", status_code=503)

    return Response(
        content=CACHE_DATA,
        media_type="application/x-mpegurl",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "public, max-age=60",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/health")
async def health():
    return {"status": "ok", "cache_age_seconds": time.time() - CACHE_TIMESTAMP}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
