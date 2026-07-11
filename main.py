# coding: utf-8
import urllib.request
import urllib.parse
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from concurrent.futures import ThreadPoolExecutor

# Tu lista real de Pastebin
PASTEBIN_URL = "https://pastebin.com/raw/Q5V2s2Rd"

# Variables globales para el Hyper-Caché en memoria RAM
CACHE_DATA = None
CACHE_TIMESTAMP = 0
CACHE_TTL = 600  # Tiempo de vida del caché: 10 minutos (600 segundos)

class ChileHyperCacheHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return  # Silencio total para no consumir ciclos de CPU

    def do_GET(self):
        global CACHE_DATA, CACHE_TIMESTAMP
        
        if self.path == '/playlist.m3u' or self.path == '/playlist':
            try:
                ahora = time.time()
                
                # ¿El caché está vacío o ya pasaron los 10 minutos?
                if CACHE_DATA is None or (ahora - CACHE_TIMESTAMP) > CACHE_TTL:
                    print("[CACHÉ] Descargando y optimizando desde Pastebin...")
                    
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (SmartHub; SMART-TV; Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) TV Safari/537.36'
                    }
                    req = urllib.request.Request(PASTEBIN_URL, headers=headers)
                    
                    with urllib.request.urlopen(req, timeout=6) as response:
                        contenido = response.read().decode('utf-8')
                    
                    lineas = contenido.splitlines()
                    
                    # Procesamiento veloz en paralelo con hilos
                    with ThreadPoolExecutor(max_workers=4) as executor:
                        resultados = list(executor.map(self.optimizar_linea, lineas))
                    
                    lista_limpia = [l for l in resultados if l is not None]
                    resultado_final = "\n".join(lista_limpia)
                    
                    # Guardamos el resultado crudo en la RAM y actualizamos la hora
                    CACHE_DATA = resultado_final.encode('utf-8')
                    CACHE_TIMESTAMP = ahora
                    print("[CACHÉ] ¡Memoria RAM actualizada con éxito!")
                else:
                    print("[CACHÉ] Sirviendo directo desde la RAM (Velocidad Rayo).")

                # Enviamos la lista que está en la RAM de inmediato
                self.send_response(200)
                self.send_header('Content-Type', 'application/x-mpegurl; charset=utf-8')
                self.send_header('Connection', 'keep-alive')
                self.send_header('Cache-Control', 'public, max-age=3600')
                self.send_header('Content-Length', str(len(CACHE_DATA)))
                self.end_headers()
                self.wfile.write(CACHE_DATA)
                
            except Exception as e:
                # Si falla Pastebin por el timeout, entregamos el caché viejo para que no se corte la tele
                if CACHE_DATA is not None:
                    print(f"[EMERGENCIA] Pastebin lento. Entregando caché de respaldo. Error: {e}")
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/x-mpegurl; charset=utf-8')
                    self.end_headers()
                    self.wfile.write(CACHE_DATA)
                else:
                    self.send_error(500, f"Error crítico de inicio: {e}")
        else:
            self.send_response(404)
            self.end_headers()

    def optimizar_linea(self, linea):
        l = linea.strip()
        if l.startswith('http://') or l.startswith('https://'):
            return l
        elif l.startswith('#EXTINF') or l.startswith('#EXTM3U'):
            return l
        return None

def run(port=8080):
    server_address = ('', port)
    httpd = HTTPServer(server_address, ChileHyperCacheHandler)
    print(f"Servidor Hyper-Caché corriendo en puerto {port}...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()

if __name__ == '__main__':
    run()
