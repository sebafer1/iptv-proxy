# coding: utf-8
import urllib.request
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from concurrent.futures import ThreadPoolExecutor

# Tu lista real de Pastebin
PASTEBIN_URL = "https://pastebin.com/raw/Q5V2s2Rd"

class ChileUltraHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return  # Cero logs para priorizar velocidad de CPU

    def do_GET(self):
        if self.path == '/playlist.m3u' or self.path == '/playlist':
            try:
                # Cabeceras premium para engañar al hosting y acelerar el enlace
                headers = {
                    'User-Agent': 'Mozilla/5.0 (SmartHub; SMART-TV; Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) TV Safari/537.36'
                }
                req = urllib.request.Request(PASTEBIN_URL, headers=headers)
                
                with urllib.request.urlopen(req, timeout=6) as response:
                    contenido = response.read().decode('utf-8')
                
                lineas = contenido.splitlines()
                
                # Procesamiento ultra rápido usando hilos en paralelo
                with ThreadPoolExecutor(max_workers=4) as executor:
                    resultados = list(executor.map(self.optimizar_linea, lineas))
                
                # Filtramos líneas vacías o None y unimos la lista
                lista_limpia = [l for l in resultados if l is not None]
                resultado_final = "\n".join(lista_limpia)
                bytes_resultado = resultado_final.encode('utf-8')
                
                # Enviar respuesta con control de caché optimizado para la TV
                self.send_response(200)
                self.send_header('Content-Type', 'application/x-mpegurl; charset=utf-8')
                self.send_header('Connection', 'keep-alive')
                self.send_header('Cache-Control', 'public, max-age=1800')  # Almacena en memoria rápida de la TV
                self.send_header('Content-Length', str(len(bytes_resultado)))
                self.end_headers()
                self.wfile.write(bytes_resultado)
                print("[PROYECTO CHILE] Lista procesada en paralelo y enviada con éxito.")
                
            except Exception as e:
                self.send_error(500, f"Error en motor paralelo: {e}")
        else:
            self.send_response(404)
            self.end_headers()

    def optimizar_linea(self, linea):
        """ Limpieza de metadatos pesados en milisegundos """
        l = linea.strip()
        if l.startswith('http://') or l.startswith('https://'):
            return l
        elif l.startswith('#EXTINF') or l.startswith('#EXTM3U'):
            return l
        return None

def run(port=8080):
    server_address = ('', port)
    httpd = HTTPServer(server_address, ChileUltraHandler)
    print(f"Servidor de Alto Rendimiento corriendo en puerto {port}...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()

if __name__ == '__main__':
    run()
