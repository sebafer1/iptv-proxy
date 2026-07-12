# coding: utf-8
import urllib.request
import time
import threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

# Tu lista real de Pastebin
PASTEBIN_URL = "https://pastebin.com/raw/Q5V2s2Rd"

# Variables globales para el Hyper-Caché en memoria RAM
CACHE_DATA = None
CACHE_TIMESTAMP = 0
CACHE_TTL = 600  # Tiempo de vida del caché: 10 minutos (600 segundos)
CACHE_LOCK = threading.Lock()  # Evita descargas duplicadas simultáneas

# Prefijos válidos dentro de un M3U ampliados
LINEAS_VALIDAS = (
    'http://', 'https://',
    '#EXTM3U', '#EXTINF',
    '#EXTGRP', '#EXTVLCOPT',
    '#EXT-X-',
)


def descargar_y_procesar():
    """Descarga la lista de Pastebin, le inyecta comandos anti-buffer y la guarda en RAM."""
    global CACHE_DATA, CACHE_TIMESTAMP

    print("[PRO-LIVE] Hilo de fondo descargando y optimizando...")
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

    # Procesamos las líneas e inyectamos los comandos directo a la RAM en segundo plano
    for linea in lineas:
        l = linea.strip()
        if l.startswith(LINEAS_VALIDAS):
            if l.startswith('#EXTINF'):
                # Inyección anti-buffer en vivo directo para el reproductor de la TV
                if "rtmp_live=" not in l:
                    l = l.replace('#EXTINF:-1', '#EXTINF:-1 cache=0 buffer=0 rtmp_live=1')
            lista_limpia.append(l)

    resultado_final = "\n".join(lista_limpia)

    CACHE_DATA = resultado_final.encode('utf-8')
    CACHE_TIMESTAMP = time.time()
    print("[PRO-LIVE] ¡Memoria RAM actualizada con éxito desde el hilo de fondo!")


def refrescar_si_hace_falta():
    """Descarga solo si el caché está vacío o expiró. Usa lock para evitar duplicados."""
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
                    print(f"[EMERGENCIA] Pastebin lento. Se mantiene caché de respaldo. Error: {e}")
                else:
                    print(f"[ERROR] Sin caché previo disponible. Falló descarga inicial: {e}")


def hilo_refresco_background():
    """Hilo esclavo en segundo plano. Mantiene la RAM fresca sin que la TV espere jamás."""
    while True:
        refrescar_si_hace_falta()
        time.sleep(30)


class ChileHyperCacheHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return  # Silencio total de CPU

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

        # Si arranca en frío el servidor y la TV pide la lista antes que el hilo de fondo termine
        if CACHE_DATA is None:
            refrescar_si_hace_falta()

        if CACHE_DATA is None:
            self.send_error(500, "Error crítico: no hay datos disponibles todavía")
            return

        # Entrega inmediata desde la RAM a velocidad luz
        self.send_response(200)
        self.send_header('Content-Type', 'application/x-mpegurl; charset=utf-8')
        self.send_header('Connection', 'keep-alive')
        self.send_header('Cache-Control', 'public, max-age=3600')
        self.send_header('Content-Length', str(len(CACHE_DATA)))
        self.end_headers()
        self.wfile.write(CACHE_DATA)


def run(port=8080):
    # Precarga síncrona obligatoria al encender el servidor para no partir en blanco
    try:
        descargar_y_procesar()
    except Exception as e:
        print(f"[AVISO] No se pudo precargar al arrancar: {e}")

    # Lanzamos el hilo de refresco asíncrono
    t = threading.Thread(target=hilo_refresco_background, daemon=True)
    t.start()

    server_address = ('', port)
    # Servidor multihilo para atender varias peticiones si es necesario
    httpd = ThreadingHTTPServer(server_address, ChileHyperCacheHandler)
    print(f"Servidor Fusionado (Background + Anti-Buffer Live) corriendo en puerto {port}...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == '__main__':
    run()
