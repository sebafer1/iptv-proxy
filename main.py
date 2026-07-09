import urllib.request
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

# Tu lista real de Pastebin
PASTEBIN_URL = "https://pastebin.com/raw/Q5V2s2Rd"

class FastRedirectHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return  # Apagar logs para máxima velocidad en Render

    def do_GET(self):
        # 1. ENTREGAR LA LISTA M3U CONFIGURADA PARA REDIRECCIÓN
        if self.path == '/playlist.m3u' or self.path == '/playlist':
            try:
                req = urllib.request.Request(PASTEBIN_URL, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=8) as response:
                    contenido = response.read().decode('utf-8')
                
                host_header = self.headers.get('Host', 'localhost:8080')
                lineas = contenido.splitlines()
                nueva_lista = []
                
                for linea in lineas:
                    if linea.startswith('http://') or linea.startswith('https://'):
                        url_encriptada = urllib.parse.quote_plus(linea)
                        nueva_lista.append(f"http://{host_header}/bypass?url={url_encriptada}")
                    else:
                        nueva_lista.append(linea)
                
                resultado_final = "\n".join(nueva_lista)
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/x-mpegurl')
                self.send_header('Content-Length', str(len(resultado_final)))
                self.end_headers()
                self.wfile.write(resultado_final.encode('utf-8'))
                print("[PLAYLIST] Entregada y lista para arranque rápido.")
            except Exception as e:
                self.send_error(500, f"Error: {e}")

        # 2. DISPARADOR DE RÁFAGA INICIAL (HTTP 302 REDIRECT)
        elif self.path.startswith('/bypass'):
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            url_original = params.get('url', [None])[0]
            
            if not url_original:
                self.send_error(400, "Falta URL.")
                return
            
            url_original = urllib.parse.unquote_plus(url_original)
            
            self.send_response(302)
            self.send_header('Location', url_original)
            self.send_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            self.send_header('Connection', 'keep-alive')
            self.end_headers()
            print("[ARRANQUE RÁPIDO] Canal redireccionado con éxito.")
        else:
            self.send_response(404)
            self.end_headers()

def run(port=8080):
    server_address = ('', port)
    httpd = HTTPServer(server_address, FastRedirectHandler)
    print(f"Servidor de Redirección Veloz corriendo en puerto {port}...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()

if __name__ == '__main__':
    run()
