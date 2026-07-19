# -*- coding: utf-8 -*-
import os
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

app = FastAPI()

app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ARCHIVO_M3U = "lista.m3u"

def procesar_lista_local() -> str:
    try:
        if not os.path.exists(ARCHIVO_M3U):
            return "#EXTM3U\n#EXTINF:-1,Archivo lista.m3u no encontrado\nhttp://localhost"
            
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
                        bloque_canal.append(linea_siguiente)
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
                    lista_limpia.extend(bloque_canal)
                    i = j + 1
                    continue
            i += 1
            
        return "\n".join(lista_limpia)
    except Exception as e:
        return f"#EXTM3U\n#EXTINF:-1,Error al procesar: {str(e)}\nhttp://localhost"

@app.get("/playlist")
@app.get("/playlist.m3u")
async def playlist():
    contenido_m3u = procesar_lista_local()
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
