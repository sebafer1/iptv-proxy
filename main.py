# -*- coding: utf-8 -*-
"""
Servidor de lista IPTV (M3U) - Versión Ultramatible para TV
"""

import os
import urllib.request
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Permitir que cualquier televisor o aplicación acceda sin bloqueos de seguridad (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PASTEBIN_URL = "https://pastebin.com/raw/Q5V2s2Rd"

def obtener_lista_limpia() -> str:
    """Descarga de Pastebin y limpia líneas vacías para la TV."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        req = urllib.request.Request(PASTEBIN_URL, headers=headers)
        with urllib.request.urlopen(req, timeout=12) as response:
            contenido = response.read().decode("utf-8", errors="ignore")
        
        lineas = contenido.splitlines()
        lista_limpia = ["#EXTM3U"]
        
        i = 0
        while i < len(lineas):
            linea = lineas[i].strip()
            if linea.startswith("#EXTINF"):
                # Buscar la URL del canal saltando líneas vacías intermedias
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
    except Exception as e:
        # Si falla, devuelve una estructura básica para que la tele no se caiga
        return "#EXTM3U\n#EXTINF:-1,Error al cargar origen\nhttp://localhost"

@app.get("/playlist")
@app.get("/playlist.m3u")
async def playlist():
    contenido_m3u = obtener_lista_limpia()
    
    # Entregamos texto plano puro, directo y con acceso total (CORS) para que la tele lo lea de inmediato
    return PlainTextResponse(
        content=contenido_m3u,
        media_type="text/plain; charset=utf-8",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )

@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
