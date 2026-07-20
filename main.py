# -*- coding: utf-8 -*-
import os
import logging
import time
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("iptv-proxy")

app = FastAPI()
app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,   # con allow_origins=["*"] esto debe ir en False
    allow_methods=["*"],
    allow_headers=["*"],
)

ARCHIVO_M3U = os.environ.get("M3U_PATH", os.path.join(os.path.dirname(__file__), "lista.m3u"))

OPCIONES_ANTIBUFFER = [
    "#EXTVLCOPT:network-caching=4000",
    "#EXTVLCOPT:live-caching=4000",
    "#EXTVLCOPT:http-reconnect=true",
    "#EXTVLCOPT:http-continuous=true",
    "#EXTVLCOPT:tcp-nodelay=true",
    "#EXTVLCOPT:ipv4-timeout=5",
    "#EXTVLCOPT:prefetch-buffer=2048",
    "#EXTVLCOPT:stream-buffer-size=16384",
    "#EXTVLCOPT:drop-late-frames=true",
    "#EXTVLCOPT:skip-frames=true",
]

# --- Caché simple en memoria basada en la fecha de modificación del archivo ---
_cache = {"mtime": None, "contenido": None}


def procesar_lista_local() -> str:
    try:
        if not os.path.exists(ARCHIVO_M3U):
            logger.warning("No se encontró %s", ARCHIVO_M3U)
            return "#EXTM3U\n#EXTINF:-1,Archivo lista.m3u no encontrado\nhttp://localhost"

        mtime = os.path.getmtime(ARCHIVO_M3U)
        if _cache["mtime"] == mtime and _cache["contenido"] is not None:
            return _cache["contenido"]

        with open(ARCHIVO_M3U, "r", encoding="utf-8", errors="ignore") as f:
            contenido = f.read()

        lineas = contenido.splitlines()
        lista_limpia = ["#EXTM3U"]

        i = 0
        while i < len(lineas):
            linea = lineas[i].strip()

            if linea.startswith("#EXTINF"):
                bloque_canal = [linea]
                j = i + 1
                enlace_encontrado = False

                while j < len(lineas):
                    linea_siguiente = lineas[j].strip()

                    if not linea_siguiente:
                        j += 1
                        continue

                    if linea_siguiente.startswith("#EXTVLCOPT"):
                        j += 1
                        continue

                    if linea_siguiente.startswith(("http://", "https://", "rtmp://", "rtsp://")):
                        bloque_canal.append(linea_siguiente)
                        enlace_encontrado = True
                        break

                    if linea_siguiente.startswith("#EXTINF"):
                        break

                    j += 1

                if enlace_encontrado:
                    # 👇 Clave: las opciones van justo ANTES de la URL de CADA canal,
                    # no una sola vez al principio del archivo.
                    lista_limpia.append(bloque_canal[0])
                    lista_limpia.extend(OPCIONES_ANTIBUFFER)
                    lista_limpia.append(bloque_canal[1])
                    i = j + 1
                    continue
            i += 1

        resultado = "\n".join(lista_limpia)
        _cache["mtime"] = mtime
        _cache["contenido"] = resultado
        return resultado

    except Exception as e:
        logger.exception("Error al procesar la lista")
        return f"#EXTM3U\n#EXTINF:-1,Error al procesar: {str(e)}\nhttp://localhost"


@app.get("/playlist")
@app.get("/playlist.m3u")
async def playlist():
    contenido_m3u = procesar_lista_local()
    return PlainTextResponse(
        content=contenido_m3u,
        media_type="application/vnd.apple.mpegurl; charset=utf-8",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/health")
async def health():
    return {"status": "ok", "archivo": ARCHIVO_M3U, "existe": os.path.exists(ARCHIVO_M3U)}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
