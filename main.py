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

# CORS
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*")
origenes = ["*"] if CORS_ORIGINS.strip() == "*" else [o.strip() for o in CORS_ORIGINS.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origenes,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def obtener_ruta_m3u() -> str:
    env_path = os.environ.get("M3U_PATH")
    if env_path:
        return env_path

    base_dir = os.path.dirname(__file__)
    
    posibles_rutas = [
        os.path.join(base_dir, "lista M3U", "lista.m3u"),
        os.path.join(base_dir, "lista M3U", "LISTA.M3U"),
        os.path.join(base_dir, "lista_m3u", "lista.m3u"),
        os.path.join(base_dir, "lista.m3u"),
        os.path.join(base_dir, "LISTA.M3U"),
    ]

    for ruta in posibles_rutas:
        if os.path.exists(ruta):
            logger.info("Archivo M3U localizado en: %s", ruta)
            return ruta

    return posibles_rutas[0]


ARCHIVO_M3U = obtener_ruta_m3u()

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

_cache = {"mtime": None, "contenido": None, "canales": 0}
_cache_lock = asyncio.Lock()


def _procesar_lista_sync(ruta_archivo: str) -> tuple[str, int]:
    if not os.path.exists(ruta_archivo):
        logger.warning("No se encontró el archivo M3U en la ruta: %s", ruta_archivo)
        return f"#EXTM3U\n#EXTINF:-1,Archivo no encontrado en {os.path.basename(ruta_archivo)}\nhttp://localhost", 0

    with open(ruta_archivo, "r", encoding="utf-8", errors="ignore") as f:
        contenido = f.read()

    lineas = contenido.splitlines()
    lista_limpia = ["#EXTM3U"]
    canales = 0

    i = 0
    while i < len(lineas):
        linea = lineas[i].strip()

        if linea.startswith("#EXTINF"):
            bloque_canal = [linea]
            extras = []
            j = i + 1
            enlace_encontrado = False

            while j < len(lineas):
                sig_linea = lineas[j].strip()
                if sig_linea.startswith("#EXTINF"):
                    break
                elif sig_linea.startswith("http://") or sig_linea.startswith("https://"):
                    bloque_canal.extend(OPCIONES_TURBO)
                    bloque_canal.extend(extras)
                    bloque_canal.append(sig_linea)
                    lista_limpia.append("\n".join(bloque_canal))
                    canales += 1
                    enlace_encontrado = True
                    i = j
                    break
                elif sig_linea:
                    extras.append(sig_linea)
                j += 1

            if not enlace_encontrado:
                i += 1
        else:
            i += 1

    return "\n".join(lista_limpia), canales


@app.get("/playlist.m3u")
@app.get("/lista.m3u")
async def obtener_playlist():
    global ARCHIVO_M3U
    
    if not os.path.exists(ARCHIVO_M3U):
        ARCHIVO_M3U = obtener_ruta_m3u()

    async with _cache_lock:
        if os.path.exists(ARCHIVO_M3U):
            mtime_actual = os.path.getmtime(ARCHIVO_M3U)
            if _cache["mtime"] == mtime_actual and _cache["contenido"] is not None:
                return PlainTextResponse(
                    _cache["contenido"],
                    media_type="application/vnd.apple.mpegurl",
                    headers={"X-Cache": "HIT"}
                )

        contenido, num_canales = await asyncio.to_thread(_procesar_lista_sync, ARCHIVO_M3U)
        
        if os.path.exists(ARCHIVO_M3U):
            _cache["mtime"] = os.path.getmtime(ARCHIVO_M3U)
            _cache["contenido"] = contenido
            _cache["canales"] = num_canales

    return PlainTextResponse(
        contenido,
        media_type="application/vnd.apple.mpegurl",
        headers={"X-Cache": "MISS"}
    )


@app.get("/health")
async def health_check():
    existe = os.path.exists(ARCHIVO_M3U)
    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "canales_cargados": _cache["canales"],
            "ruta_m3u": ARCHIVO_M3U,
            "archivo_existe": existe
        }
    )
