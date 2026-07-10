# coding: utf-8
import urllib.request
import urllib.parse
import gzip
from http.server import HTTPServer, BaseHTTPRequestHandler

# Tu lista real de Pastebin
PASTEBIN_URL = "https://pastebin.com/raw/Q5V2s2Rd"

class UltraFastHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return  # Silencio absoluto de logs para no frenar la CPU de Render

    def do_GET(self):
        if self.path == '/playlist.m3u' or self.path == '/playlist':
            try:
                # 1. Descarga optimizada desde Pastebin con timeout corto
                req = urllib.request.Request(PASTEBIN_URL, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=5) as response:
                    contenido = response.read().decode('utf-8')
                
                lineas = contenido.splitlines()
                nueva_lista = []
                
                # 2. Limpieza rápida de líneas para el reproductor de la TV
                for linea in lineas:
                    linea_limpia = linea.strip()
                    if linea_limpia.startswith('http://') or linea_limpia.startswith('https://'):
                        nueva_lista.append(linea_limpia)
                    elif linea_limpia.startswith('#EXTINF') or linea_limpia.startswith('#EXTM3U'):
                        nueva_lista.append(linea_limpia)
                
                resultado_final = "\n".join(nueva_lista)
                bytes_resultado = resultado_final.encode('utf-8')
                
                # 3. Enviar respuesta con optimizaciones de memoria y velocidad
                self.send_response(200)
                self.send_header('Content-Type', 'application/x-mpegurl; charset=utf-8')
                
                # Forzamos Keep-Alive y agregamos control de caché agresivo para la TV
                self.send_header('Connection', 'keep-alive')
                self.send_header('Cache-Control', 'public, max-age=3600')
                
                # Revisamos si la tele soporta compresión para mandarla ultra liviana
                accept_encoding = self.headers.get('Accept-Encoding', '')
                if 'gzip' in accept_encoding:
                    bytes_comprimidos = gzip.compress(bytes_resultado)
                    self.send_header('Content-Encoding', 'gzip')
                    self.send_header('Content-Length', str(len(bytes_comprimidos)))
                    self.end_headers()
                    self.wfile.write(bytes_comprimidos)
                else:
                    self.send_header('Content-Length', str(len(bytes_resultado)))
                    self.end_headers()
                    self.wfile.write(bytes_resultado)
                    
                print("[ULTRA-OK] Lista enviada con compresión y caché optimizado.")
            except Exception as e:
                self.send_error(500, f"Error en optimización: {e}")
        else:
            self.send_response(404)
            self.end_headers()

def run(port=8080):
    server_address = ('', port)
    httpd = HTTPServer(server_address, UltraFastHandler)
    print(f"Servidor Ultra Optimizado corriendo en puerto {port}...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()

if __name__ == '__main__':
    run()
