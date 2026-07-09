import urllib.request
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
import threading
import time
import gzip

# Configuración - Tu lista real de Pastebin
PASTEBIN_URL = "https://pastebin.com/raw/Q5V2s2Rd"
CACHE_TTL_SECONDS = 300  # La lista se actualiza en caché cada 5 minutos

# Variables globales para el sistema de Caché Inteligente
cache_data = None
cache_timestamp = 0
cache_lock = threading.Lock()

def obtener_lista_m3u():
    """Obtiene la lista de Pastebin con caché inteligente y validación"""
    global cache_data, cache_timestamp
    ahora = time.time()
    
    with cache_lock:
        # Si la caché está vigente, la entrega de inmediato (Tiempo de respuesta casi 0)
        if cache_data and (ahora - cache_timestamp < CACHE_TTL_SECONDS):
            return cache_data
        
        # Si venció o no existe, va a buscar a Pastebin con un Timeout optimizado
        try:
            req = urllib.request.Request(PASTEBIN_URL, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                contenido = response.read().decode('utf-8')
            
            # Validación simple: Verificar si tiene la cabecera M3U
            if "#EXTM3U" in contenido:
                cache_data = contenido
                cache_timestamp = ahora
                print("[CACHÉ] Lista M3U actualizada y validada correctamente.")
                return cache_data
            else:
                print("[ALERTA] La lista descargada no es válida. Usando caché antigua.")
        except Exception as e:
            print(f"[ERROR] No se pudo actualizar desde Pastebin: {e}. Usando respaldo en caché.")
        
        # Si falla la descarga, retorna lo que tenga en caché para no dejar la tele en negro
        return cache_data if cache_data else "#EXTM3U\n#EXTINF:-1,Servidor Iniciando... Intente de nuevo"

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Servidor HTTP Multihilo: Atiende múltiples clientes en segundo plano sin bloquearse"""
    daemon_threads = True

class AdvancedHybridHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Mantiene los logs limpios para bajo consumo de CPU
        return

    def do_GET(self):
        # RUTA OPTIMIZADA PARA ENTREGAR LA LISTA M3U
        if self.path == '/playlist.m3u' or self.path == '/playlist':
            inicio = time.time()
            contenido_m3u = obtener_lista_m3u()
            
            # Procesar el contenido (Mantiene el flujo de video directo para evitar cortes)
            lineas = contenido_m3u.splitlines()
            nueva_lista = []
            for linea in lineas:
                nueva_lista.append(linea)
            
            resultado_final = "\n".join(nueva_lista).encode('utf-8')
            
            # Revisar si el cliente (la tele) soporta compresión GZIP
            accept_encoding = self.headers.get('Accept-Encoding', '')
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/x-mpegurl')
            
            if 'gzip' in accept_encoding:
                # Compresión GZIP en tiempo real para máxima velocidad de transferencia
                resultado_final = gzip.compress(resultado_final)
                self.send_header('Content-Encoding', 'gzip')
            
            self.send_header('Content-Length', str(len(resultado_final)))
            self.send_header('Connection', 'keep-alive')  # Conexión persistente HTTP
            self.end_headers()
            self.wfile.write(resultado_final)
            
            latencia = (time.time() - inicio) * 1000
            print(f"[ESTADÍSTICAS] Lista entregada en {latencia:.2f}ms")
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Ruta no encontrada.")

def run(port=8080):
    # Precarga inicial de la lista al arrancar el servidor
    obtener_lista_m3u()
    server_address = ('', port)
    httpd = ThreadedHTTPServer(server_address, AdvancedHybridHandler)
    print(f"[INICIO] Servidor Avanzado Multihilo corriendo en puerto {port}...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()

if __name__ == '__main__':
    run()
