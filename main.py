import urllib.request
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

# Tu lista real de Pastebin
PASTEBIN_URL = "https://pastebin.com/raw/Q5V2s2Rd"

class PureHybridHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return  # Desactiva logs para que Render no consuma CPU

    def do_GET(self):
        # El servidor SOLO trabaja para procesar el texto de la lista M3U
        if self.path == '/playlist.m3u' or self.path == '/playlist':
            try:
                # Descarga tu Pastebin emulando un navegador seguro
                req = urllib.request.Request(PASTEBIN_URL, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=8) as response:
                    contenido = response.read().decode('utf-8')
                
                lineas = contenido.splitlines()
                nueva_lista = []
                
                for linea in lineas:
                    # MANTIENE LOS ENLACES DIRECTOS
                    # Al no usar la ruta '/stream', el video va directo de la fuente a tu tele.
                    # ¡Esto ELIMINA por completo los 10 segundos de buffer internacional!
                    if linea.startswith('http://') or linea.startswith('https://'):
                        nueva_lista.append(linea)
                    else:
                        nueva_lista.append(linea)
                
                resultado_final = "\n".join(nueva_lista)
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/x-mpegurl')
                self.send_header('Content-Length', str(len(resultado_final)))
                self.end_headers()
                self.wfile.write(resultado_final.encode('utf-8'))
            except Exception as e:
                self.send_error(500, f"Error generando lista: {e}")
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Ruta no encontrada.")

def run(port=8080):
    server_address = ('', port)
    httpd = HTTPServer(server_address, PureHybridHandler)
    print(f"Servidor Hibrido Puro (Sin Buffer) iniciado en el puerto {port}...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()

if __name__ == '__main__':
    run()
