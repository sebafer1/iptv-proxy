# -*- coding: utf-8 -*-
"""
Servidor IPTV - Versión Zapping Turbo (Ultra Antibuffer & Low Delay)
"""

import os
import urllib.request
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

app = FastAPI()

# 1. EFECTO ANTIBUFFER: Comprime los datos para que viajen el triple de rápido
app.add_middleware(GZipMiddleware, minimum_size=500)

# 2. CORS COMPLETAMENTE ABIERTO: Evita retrasos de validación en Smart TVs
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# TU NUEVA LISTA DE PASTEBIN INTEGRADA
PASTEBIN_URL = "https://pastebin.com/raw/azR86LBR"

def procesar_lista_turbo() -> str:
    """Descarga, filtra y procesa los canales en milisegundos sin delay."""
    try:
        # Cabeceras optimizadas para respuesta inmediata
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Encoding": "gzip, deflate"
        }
        req = urllib.request.Request(PASTEBIN_URL, headers=headers)
        
        # Timeout corto (5s) para que si un canal traba, el servidor no se quede esperando
        with urllib.request.urlopen(req, timeout=5) as response:
            contenido = response.read().decode("utf-8", errors="ignore")
        
        lineas = contenido.splitlines()
        lista_limpia = ["#EXTM3U"]
        
        i = 0
        while i < len(lineas):
            linea = lineas[i].strip()
            if linea.startswith("#EXTINF"):
                j = i + 1
                while j < len(lineas) and not lineas[j].strip():
                    j += 1
                
                if j < len(lineas):
                    siguiente = lineas[j].strip()
                    if siguiente.startswith(("http://", "https://", "rtmp://", "rtsp://")):
                        lista_limpia.append(linea)
                        lista_limpia.append(siguiente)
                        i = j + 1
                        continue
            i += 1
            
        return "\n".join(lista_limpia)
    except Exception:
        # En caso de caída extrema, responde al instante con una lista vacía para no congelar la app
        return "#EXTM3U\n#EXTINF:-1,Servidor Reconectando...\nhttp://localhost"

@app.get("/playlist")
@app.get("/playlist.m3u")
async def playlist():
    contenido_m3u = procesar_lista_turbo()
    
    # 3. DIRECTO A LA TELE: Cabeceras de caché agresivas para que la App no almacene basura (Antibuffer)
    return PlainTextResponse(
        content=contenido_m3u,
        media_type="text/plain; charset=utf-8",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
            "Connection": "keep-alive"
        }
    )

@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
