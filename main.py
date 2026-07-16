# -*- coding: utf-8 -*-
"""
Servidor de lista IPTV (M3U) - Versión Optimizada y Libre de Token
"""

import os
import time
import asyncio
import logging
import urllib.request
from collections import defaultdict

from fastapi import FastAPI, Request
from fastapi.responses import Response, PlainTextResponse
from fastapi.middleware.gzip import GZipMiddleware

# ------------------------------------------------------------------
# Configuración
# ------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("iptv")

# Tu URL real de Pastebin
PASTEBIN_URL = "https://pastebin.com/raw/Q5V2s2Rd"

CACHE_TTL = 300          # Refrescar caché cada 5 minutos
REFRESH_INTERVAL = 30    # Revisión en segundo plano cada 30 segundos

# Rate limiting por IP para evitar saturación
RATE_LIMIT_MAX = 30
RATE_LIMIT_WINDOW = 10   # segundos

# ------------------------------------------------------------------
# Estado en memoria (Caché + Rate Limit)
# ------------------------------------------------------------------
CACHE_DATA: bytes | None = None
CACHE_TIMESTAMP: float = 0.0
CACHE_LOCK = asyncio.Lock()

_rate_hits: dict[str, list[float]] = defaultdict(list)


def _descargar_y_procesar_sync() -> bytes:
    """Descarga la lista original y asegura que se mantengan los nombres de los canales."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    req = urllib.request.Request(PASTEBIN_URL, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as response:
        contenido = response.read().decode("utf-8", errors="ignore")

    lineas = contenido.splitlines()
    lista_limpia = []
    
    # Cabecera obligatoria
    lista_limpia.append("#EXTM3U")
    
    i = 0
    while i < len(lineas):
        linea = lineas[i].strip()
        
        # Si es la metadata del canal (#EXTINF), la guardamos junto con su link
        if linea.startswith("#EXTINF"):
            if i + 1 < len(lineas) and lineas[i+1].strip().startswith(("http://", "https://")):
                lista_limpia.append(linea)                      # Guarda el nombre/logo del canal
                lista_limpia.append(lineas[i+1].strip())       # Guarda la URL de transmisión
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
            log.info("Caché actualizada correctamente en RAM.")
        except Exception as e:
            if CACHE_DATA is not None:
                log.warning("Fallo al conectar con Pastebin. Usando copia guardada en RAM: %s", e)
            else:
                log.error("Fallo crítico: No se pudo obtener la lista inicial: %s", e)


async def hilo_refresco_background():
    """Mantiene los canales actualizados en segundo plano."""
    while True:
        await refrescar_cache()
        await asyncio.sleep(REFRESH_INTERVAL)


def rate_limit_ok(ip: str) -> bool:
    """Evita que peticiones repetidas bloqueen el servidor."""
    ahora = time.time()
    hits = _rate_hits[ip]
    while hits and ahora - hits[0] > RATE_LIMIT_WINDOW:
        hits.pop(0)
    if len(hits) >= RATE_LIMIT_MAX:
        return False
    hits.append(ahora)
    return True


# ------------------------------------------------------------------
# Servidor FastAPI
# ------------------------------------------------------------------
app = FastAPI()
app.add_middleware(GZipMiddleware, minimum_size=500)


@app.on_event("startup")
async def startup():
    await refrescar_cache(forzar=True)
    asyncio.create_task(hilo_refresco_background())
    log.info("Servidor IPTV Iniciado y listo.")


@app.get("/playlist")
@app.get("/playlist.m3u")
async def playlist(request: Request):
    # Control de peticiones por IP
    ip = request.client.host if request.client else "desconocido"
    if not rate_limit_ok(ip):
        return PlainTextResponse("Demasiados intentos. Espera unos segundos.", status_code=429)

    if CACHE_DATA is None:
        await refrescar_cache(forzar=True)

    if CACHE_DATA is None:
        return PlainTextResponse("Servicio no disponible temporalmente.", status_code=503)

    return Response(
        content=CACHE_DATA,
        media_type="text/plain",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Content-Disposition": "attachment; filename=playlist.m3u",
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
