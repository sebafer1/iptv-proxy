# coding: utf-8
import urllib.request
import time
import threading
import logging
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

# Configuración de logging profesional (reemplaza a los prints y no consume CPU)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Tu lista real de Pastebin
PASTEBIN_URL = "https://pastebin.com/raw/Q5V2s2Rd"

# Variables globales para el Hyper-Caché en memoria RAM
CACHE_DATA = None
CACHE_TIMESTAMP = 0
CACHE_TTL = 600  # 10 minutos de vida del caché
CACHE_LOCK = threading.Lock()

# Prefijos estándar y estrictos de la norma M3U
LINEAS_VALIDAS = (
    'http://', 'https://',
    '#EXTM3U', '#EXTINF',
    '#EXTGRP', '#EXTVLCOPT',
    '#EXT-X-',
)

def descargar_y_procesar():
    """Descarga, limpia de forma estándar y almacena en RAM de manera eficiente."""
    global CACHE_DATA, CACHE_TIMESTAMP

    logging.info("Hilo de fondo: Actualizando lista desde origen de forma limpia.")
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
            # Mantenemos la playlist 100% estándar, limpia y compatible con cualquier TV
            lista_limpia.append(l)

    resultado_final = "\n".join(lista_limpia)

    CACHE_DATA = resultado_final.encode('utf-8')
    CACHE_TIMESTAMP = time.time()
    logging.info("Caché en RAM actualizado con éxito.")

def refrescar_si_hace_falta():
    """Control de vigencia del caché con bloqueo de seguridad."""
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
                    logging.warning(f"Origen lento. Manteniendo caché de respaldo. Detalle: {e}")
                else:
                    logging.error(f"Error crítico en arranque inicial: {e}")

def hilo_refresco_background():
    """Hilo esclavo en segundo plano: mantiene la lista al día en silencio."""
    while True:
        refrescar_si_hace_falta()
        time.sleep(30)

class ChileUltraStandardHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return  # Desactiva los logs por cada petición de la TV para máxima velocidad

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
            self.send_error(500, "Datos no disponibles temporalmente")
            return

        # Despacho instantáneo y óptimo desde la memoria RAM
        self.send_response(200)
        self.send_header('Content-Type', 'application/x-mpegurl; charset=utf-8')
        self.send_header('Connection', 'keep-alive')
        self.send_header('Cache-Control', 'public, max-age=3600')
        self.send_header('Content-Length', str(len(CACHE_DATA)))
        self.end_headers()
        self.wfile.write(CACHE_DATA)

def run(port=8080):
    try:
        descargar_y_procesar()
    except Exception as e:
        logging.warning(f"No se pudo precargar la lista al iniciar: {e}")

    t = threading.Thread(target=hilo_refresco_background, daemon=True)
    t.start()

    server_address = ('', port)
    httpd = ThreadingHTTPServer(server_address, ChileUltraStandardHandler)
    logging.info(f"Servidor Profesional Estándar corriendo en puerto {port}...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()

if __name__ == '__main__':
    run()
