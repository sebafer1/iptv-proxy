import urllib.request
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

# Tu lista real de Pastebin
PASTEBIN_URL = "https://pastebin.com/raw/Q5V2s2Rd"

class PureHybridHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def do_GET(self):
        if self.path == '/playlist.m3u' or self.path == '/playlist':
            try:
                req = urllib.request.Request(PASTEBIN_URL, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=8) as response:
                    contenido = response.read().decode('utf-8')
                
                lineas = contenido.splitlines()
                nueva_lista = []
                
                for linea in lineas:
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
                self.send_error(500, f"Error: {e}")
        else:
            self.send_response(404)
            self.end_headers()

def run(port=8080):
    server_address = ('', port)
    httpd = HTTPServer(server_address, PureHybridHandler)
    print(f"Servidor corriendo en puerto {port}...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()

if __name__ == '__main__':
    run()
