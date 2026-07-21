# -*- coding: utf-8 -*-
import os
import logging
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("iptv-proxy-turbo")

app = FastAPI(title="IPTV Proxy Ultra Speed")

# Compresión GZip para transferencia ultra rápida del archivo M3U
app.add_middleware(GZipMiddleware, minimum_size=256)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

ARCHIVO_M3U = os.environ.get("M3U_PATH", os.path.join(os.path.dirname(__file__), "lista.m3u"))

# Directivas avanzadas Anti-Buffer y de Cambio Rápido de Canal (Low-Latency)
OPCIONES_TURBO = [
    "#EXTVLCOPT:network-caching=2000",       # Colchón optimizado para respuesta rápida
    "#EXTVLCOPT:live-caching=2000",          # Carga fluida en transmisiones en vivo
    "#EXTVLCOPT:clock-synchro=0",            # Desactiva la espera de reloj para inicio instantáneo
    "#EXTVLCOPT:http-reconnect=true",        # Auto-reconexión inmediata ante caídas breves
    "#EXTVLCOPT:http-continuous=true",       # Flujo de datos HTTP ininterrumpido
    "#EXTVLCOPT:tcp-nodelay=true",           # Envío inmediato de paquetes TCP sin latencia
    "#EXTVLCOPT:ipv4-timeout=3",             # Cancelación y reintento rápido si un servidor no responde
    "#EXTVLCOPT:prefetch-buffer=4096",       # Pre-carga en caché de paquetes de video
    "#EXTVLCOPT:stream-buffer-size=32768",   # Búfer extendido a 32KB en memoria RAM
    "#EXTVLCOPT:drop-late-frames=true",      # Salta cuadros con retraso para mantener tiempo real
    "#EXTVLCOPT:skip-frames=true",            # Previene congelamientos de pantalla
    "#EXTVLCOPT:http-user-agent=VLC/3.0.20 LibVLC/3.0.20" # Camuflaje de cliente para evitar bloqueos
]

# Caché inteligente en memoria para respuesta a nivel de milisegundos
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
                    lista_limpia.append(bloque_canal[0])
                    lista_limpia.extend(OPCIONES_TURBO)
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
            "Connection": "keep-alive"
        },
    )

@app.get("/health")
async def health():
    return {"status": "ok", "archivo": ARCHIVO_M3U, "existe": os.path.exists(ARCHIVO_M3U)}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
