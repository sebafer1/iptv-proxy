import urllib.request
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
import sys

# Configuración de Origen
PASTEBIN_URL = "https://pastebin.com/raw/d8uWicf4"  # Tu lista original con los enlaces de looknowsytes

class TurboProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Desactiva los logs repetitivos en Render para máxima velocidad
        return

    def do_GET(self):
        # 1. RUTA PARA ENTREGAR LA LISTA M3U OPTIMIZADA
        if self.path == '/playlist.m3u' or self.path == '/playlist':
            try:
                req = urllib.request.Request(PASTEBIN_URL, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=10) as response:
                    contenido = response.read().decode('utf-8')
                
                # Reescritura Turbo: Reemplaza la base original por la URL de tu proxy en Render
                host_header = self.headers.get('Host', 'localhost:8080')
                lineas = contenido.splitlines()
                nueva_lista = []
                
                for linea in lineas:
                    if linea.startswith('http://') or linea.startswith('https://'):
                        # Codifica la URL original de looknowsytes para pasarla de forma segura como parámetro
                        url_encriptada = urllib.parse.quote_plus(linea)
                        nueva_lista.append(f"http://{host_header}/stream?url={url_encriptada}")
                    else:
                        nueva_lista.append(linea)
                
                resultado_final = "\n".join(nueva_lista)
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/x-mpegurl')
                self.send_header('Content-Length', str(len(resultado_final)))
                self.end_headers()
                self.wfile.write(resultado_final.encode('utf-8'))
            except Exception as e:
                self.send_error(500, f"Error generando lista Turbo: {e}")

        # 2. RUTA DE TRANSMISIÓN TURBO (PASS-THROUGH EN TIEMPO REAL)
        elif self.path.startswith('/stream'):
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            url_original = params.get('url', [None])[0]
            
            if not url_original:
                self.send_error(400, "Falta el parametro URL de transmision.")
                return
                
            try:
                # Quitamos cualquier decodificación excesiva
                url_original = urllib.parse.unquote_plus(url_original)
                
                # Abrimos el canal directo a looknowsytes emulando un reproductor estándar
                req = urllib.request.Request(
                    url_original, 
                    headers={'User-Agent': 'IPTVSmarters/1.0', 'Accept': '*/*'}
                )
                
                with urllib.request.urlopen(req, timeout=15) as stream_response:
                    # Heredamos las cabeceras esenciales del stream de video original
                    self.send_response(200)
                    for header in ['Content-Type', 'Content-Length', 'Connection']:
                        val = stream_response.headers.get(header)
                        if val:
                            self.send_header(header, val)
                    self.end_headers()
                    
                    # SISTEMA TURBO: Transferencia directa por bloques en tiempo real
                    while True:
                        chunk = stream_response.read(65536)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        
            except Exception as e:
                try:
                    self.send_error(500, f"Error en Stream Turbo: {e}")
                except:
                    pass
        else:
            self.send_error(404, "Ruta no encontrada en el Proxy Turbo.")

def run(server_class=HTTPServer, handler_class=TurboProxyHandler, port=8080):
    server_address = ('', port)
    httpd = server_class(server_address, handler_class)
    print(f"Servidor Proxy IPTV Versión Turbo iniciado en el puerto {port}...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()

if __name__ == '__main__':
    run()
