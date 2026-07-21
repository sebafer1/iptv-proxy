# -*- coding: utf-8 -*-
import os
import asyncio
import logging
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("iptv-proxy-turbo")

app = FastAPI(title="IPTV Proxy Ultra Speed")

app.add_middleware(GZipMiddleware, minimum_size=256)

# CORS configurable por entorno (por defecto abierto, como el original)
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*")
origenes = ["*"] if CORS_ORIGINS.strip() == "*" else [o.strip() for o in CORS_ORIGINS.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origenes,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

ARCHIVO_M3U = os.environ.get("M3U_PATH", os.path.join(os.path.dirname(__file__), "lista.m3u"))

# Directivas Anti-Buffer y de Cambio Rápido de Canal (Low-Latency)
OPCIONES_TURBO = [
    "#EXTVLCOPT:network-caching=2000",
    "#EXTVLCOPT:live-caching=2000",
    "#EXTVLCOPT:clock-synchro=0",
    "#EXTVLCOPT:http-reconnect=true",
    "#EXTVLCOPT:http-continuous=true",
    "#EXTVLCOPT:tcp-nodelay=true",
    "#EXTVLCOPT:ipv4-timeout=3",
    "#EXTVLCOPT:prefetch-buffer=4096",
    "#EXTVLCOPT:stream-buffer-size=32768",
    "#EXTVLCOPT:drop-late-frames=true",
    "#EXTVLCOPT:skip-frames=true",
    "#EXTVLCOPT:http-user-agent=VLC/3.0.20 LibVLC/3.0.20",
]

# Caché en memoria + lock para evitar condiciones de carrera en refrescos concurrentes
_cache = {"mtime": None, "contenido": None, "canales": 0}
_cache_lock = asyncio.Lock()


def _procesar_lista_sync() -> tuple[str, int]:
    """Lee y reescribe el M3U. Corre en threadpool para no bloquear el event loop."""
    if not os.path.exists(ARCHIVO_M3U):
        logger.warning("No se encontró %s", ARCHIVO_M3U)
        return "#EXTM3U\n#EXTINF:-1,Archivo lista.m3u no encontrado\nhttp://localhost", 0

    with open(ARCHIVO_M3U, "r", encoding="utf-8", errors="ignore") as f:
        contenido = f.read()

    lineas = contenido.splitlines()
    lista_limpia = ["#EXTM3U"]
    canales = 0

    i = 0
    while i < len(lineas):
        linea = lineas[i].strip()

        if linea.startswith("#EXTINF"):
            bloque_canal = [linea]
            extras = []  # líneas tipo #EXTGRP, #KODIPROP, etc. que NO deben perderse
            j = i + 1
            enlace_encontrado = False

            while j < len(lineas):
                linea_siguiente = lineas[j].strip()

                if not linea_siguiente:
                    j += 1
                    continue

                # Las EXTVLCOPT originales se descartan: las reemplazamos por las turbo
                if linea_siguiente.startswith("#EXTVLCOPT"):
                    j += 1
                    continue

                if linea_siguiente.startswith(("http://", "https://", "rtmp://", "rtsp://")):
                    bloque_canal.append(linea_siguiente)
                    enlace_encontrado = True
                    break

                if linea_siguiente.startswith("#EXTINF"):
                    break

                # Cualquier otra directiva (#EXTGRP, #KODIPROP, #EXTGRP:, etc.) se conserva
                if linea_siguiente.startswith("#"):
                    extras.append(linea_siguiente)

                j += 1

            if enlace_encontrado:
                lista_limpia.append(bloque_canal[0])
                lista_limpia.extend(extras)
                lista_limpia.extend(OPCIONES_TURBO)
                lista_limpia.append(bloque_canal[1])
                canales += 1
                i = j + 1
                continue
        i += 1

    return "\n".join(lista_limpia), canales


async def obtener_lista(forzar: bool = False) -> str:
    try:
        if not os.path.exists(ARCHIVO_M3U):
            return "#EXTM3U\n#EXTINF:-1,Archivo lista.m3u no encontrado\nhttp://localhost"

        mtime = os.path.getmtime(ARCHIVO_M3U)

        if not forzar and _cache["mtime"] == mtime and _cache["contenido"] is not None:
            return _cache["contenido"]

        async with _cache_lock:
            # Revalidar dentro del lock por si otra request ya actualizó la caché
            if not forzar and _cache["mtime"] == mtime and _cache["contenido"] is not None:
                return _cache["contenido"]

            resultado, canales = await asyncio.to_thread(_procesar_lista_sync)
            _cache["mtime"] = mtime
            _cache["contenido"] = resultado
            _cache["canales"] = canales
            return resultado

    except Exception as e:
        logger.exception("Error al procesar la lista")
        return f"#EXTM3U\n#EXTINF:-1,Error al procesar: {str(e)}\nhttp://localhost"


@app.get("/playlist")
@app.get("/playlist.m3u")
async def playlist():
    contenido_m3u = await obtener_lista()
    return PlainTextResponse(
        content=contenido_m3u,
        media_type="application/vnd.apple.mpegurl; charset=utf-8",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
            "Connection": "keep-alive",
        },
    )


@app.post("/reload")
async def reload_playlist():
    """Fuerza la relectura del M3U ignorando la caché por mtime."""
    contenido_m3u = await obtener_lista(forzar=True)
    return JSONResponse({"status": "ok", "canales": _cache["canales"], "bytes": len(contenido_m3u)})


@app.get("/health")
async def health():
    existe = os.path.exists(ARCHIVO_M3U)
    return {
        "status": "ok" if existe else "warning",
        "archivo": ARCHIVO_M3U,
        "existe": existe,
        "canales_en_cache": _cache["canales"],
        "cache_activa": _cache["contenido"] is not None,
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
