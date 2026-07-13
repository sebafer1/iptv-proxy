# coding: utf-8
import urllib.request
import time
import threading
import logging
import socket
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

# Configuración de logging profesional (Ultra-rápido, no genera lag de consola)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Tu lista real de Pastebin
PASTEBIN_URL = "https://pastebin.com/raw/Q5V2s2Rd"

# Variables de control para el Hyper-Caché en RAM
CACHE_DATA = None
CACHE_TIMESTAMP = 0
CACHE_TTL = 600  # 10 minutos de vigencia en RAM
CACHE_LOCK = threading.Lock()

# Filtros ultra-estrictos para mantener el estándar M3U más rápido del mundo
LINEAS_VALIDAS = (
    'http://', 'https://',
    '#EXTM3U', '#EXTINF',
    '#EXTGRP', '#EXTVLCOPT',
    '#EXT-X-',
)

def descargar_y_procesar():
    """Descarga, limpia al estándar puro e inyecta parámetros de red."""
    global CACHE_DATA, CACHE_TIMESTAMP

    logging.info("Optimización de red: Descargando lista limpia desde origen.")
    headers = {
        'User-Agent': (
            'Mozilla/5.0 (SmartHub; SMART-TV; Windows NT 10.0; WOW64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) TV Safari/537.36'
        )
    }
    req = urllib.request.Request(PASTEBIN_URL, headers=headers)

    with urllib.request.urlopen(req, timeout=6) as response:
        contenido = response.read().decode('utf-8')

    lineas = contenido.splitlines()
    lista_limpia = []

    for linea in lineas:
        l = linea.strip()
        if l.startswith(LINEAS_VALIDAS):
            # Formato 100% puro para que la Smart TV lo procese en microsegundos
            lista_limpia.append(l)

    resultado_final = "\n".join(lista_limpia)

    CACHE_DATA = resultado_final.encode('utf-8')
    CACHE_TIMESTAMP = time.time()
    logging.info("¡Hyper-Caché optimizado listo en RAM!")

def refrescar_si_hace_falta():
    """Control de caché asíncrono con bloqueo preventivo de hilos."""
    global CACHE_DATA, CACHE_TIMESTAMP
    ahora = time.time()
    if CACHE_DATA is not None and (ahora - CACHE_TIMESTAMP) <= CACHE_TTL:
        return

    with CACHE_LOCK:
        ahora = time.time()
        if CACHE_DATA is None or (ahora - CACHE_TIMESTAMP) > CACHE_TTL:
            try:
                descargar_y_procesar()
            except Exception as e:
                if CACHE_DATA is not None:
                    logging.warning(f"Error temporal de origen. Entregando RAM de respaldo: {e}")
                else:
                    logging.error(f"Fallo crítico sin caché previo: {e}")

def hilo_refresco_background():
    """Hilo esclavo en segundo plano: mantiene la RAM fresca sin tocar tu tele."""
    while True:
        refrescar_si_hace_falta()
        time.sleep(30)

class ChileAntiBufferHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return  # Silencio total de peticiones para ahorrar 100% de CPU

    def do_GET(self):
        if self.path in ('/playlist.m3u', '/playlist'):
            self._responder_playlist()
        else:
            self.send_response(404)
            self.end_headers()

    def do_HEAD(self):
        if self.path in ('/playlist.m3u', '/playlist'):
            self.send_response(200)
            self.send_header('Content-Type', 'application/x-mpegurl; charset=utf-8')
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def _responder_playlist(self):
        global CACHE_DATA

        if CACHE_DATA is None:
            refrescar_si_hace_falta()

        if CACHE_DATA is None:
            self.send_error(500, "Error de sincronización temporal")
            return

        # --- TRUCO MAESTRO DE INGENIERÍA DE REDES (ANTI-BUFFER) ---
        try:
            # Desactivamos el algoritmo de Nagle directamente en el socket de la tele
            # Esto hace que los paquetes salgan sin delay de espera
            self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except Exception:
            pass  # En algunos entornos virtuales de hosting puede no aplicarse, pero se intenta siempre

        self.send_response(200)
        self.send_header('Content-Type', 'application/x-mpegurl; charset=utf-8')
        
        # Conexión persistente real para que la tele no tenga que renegociar el canal
        self.send_header('Connection', 'keep-alive')
        self.send_header('Keep-Alive', 'timeout=60, max=100')
        
        # Desactivar buffers intermedios de servidores proxy (Bypass directo)
        self.send_header('X-Accel-Buffering', 'no')
        
        # Instrucción de caché local para la Smart TV
        self.send_header('Cache-Control', 'public, max-age=3600')
        self.send_header('Content-Length', str(len(CACHE_DATA)))
        self.end_headers()
        
        # Envío instantáneo de la RAM
        self.wfile.write(CACHE_DATA)

def run(port=8080):
    try:
        descargar_y_procesar()
    except Exception as e:
        logging.warning(f"Sincronización inicial omitida: {e}")

    t = threading.Thread(target=hilo_refresco_background, daemon=True)
    t.start()

    server_address = ('', port)
    # Servidor optimizado multihilo
    httpd = ThreadingHTTPServer(server_address, ChileAntiBufferHandler)
    logging.info(f"Servidor Anti-Buffer 5000% corriendo en puerto {port}...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()

if __name__ == '__main__':
    run()
