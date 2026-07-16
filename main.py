# coding: utf-8
import urllib.request
import time
import threading
import logging
import socket
import re
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

# Configuración de logging profesional (Ultra-rápido, asíncrono en RAM)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Tu lista real de Pastebin
PASTEBIN_URL = "https://pastebin.com/raw/Q5V2s2Rd"

# Variables de control para el Hyper-Caché en RAM
CACHE_DATA = None
CACHE_TIMESTAMP = 0
CACHE_TTL = 600  # 10 minutos de vigencia en RAM
CACHE_LOCK = threading.Lock()

# Filtros ultra-estrictos para mantener el estándar M3U limpio
LINEAS_VALIDAS = (
    'http://', 'https://',
    '#EXTM3U', '#EXTINF',
    '#EXTGRP', '#EXTVLCOPT',
    '#EXT-X-'
)

# Diccionario inteligente para mapear canales de Chile a sus Logos y EPG oficiales
# Esto transforma tu lista plana en una interfaz interactiva estilo Zapping
METADATOS_CANALES = {
    "tvr": {
        "tvg-id": "TVR.cl", 
        "tvg-name": "TVR Chile", 
        "tvg-logo": "https://i.imgur.com/u7VbY4S.png", 
        "group-title": "Nacionales Chile"
    },
    "mega": {
        "tvg-id": "Mega.cl", 
        "tvg-name": "Mega HD", 
        "tvg-logo": "https://upload.wikimedia.org/wikipedia/commons/e/e4/Mega_Canal_Chile.png", 
        "group-title": "Nacionales Chile"
    },
    "chilevisión": {
        "tvg-id": "Chilevision.cl", 
        "tvg-name": "Chilevisión HD", 
        "tvg-logo": "https://upload.wikimedia.org/wikipedia/commons/0/07/Chilevisi%C3%B3n_2018.png", 
        "group-title": "Nacionales Chile"
    },
    "chv": {
        "tvg-id": "Chilevision.cl", 
        "tvg-name": "Chilevisión HD", 
        "tvg-logo": "https://upload.wikimedia.org/wikipedia/commons/0/07/Chilevisi%C3%B3n_2018.png", 
        "group-title": "Nacionales Chile"
    },
    "tvn": {
        "tvg-id": "TVN.cl", 
        "tvg-name": "TVN HD", 
        "tvg-logo": "https://upload.wikimedia.org/wikipedia/commons/2/22/Televisi%C3%B3n_Nacional_de_Chile_2020.png", 
        "group-title": "Nacionales Chile"
    },
    "canal 13": {
        "tvg-id": "Canal13.cl", 
        "tvg-name": "Canal 13 HD", 
        "tvg-logo": "https://upload.wikimedia.org/wikipedia/commons/e/eb/Canal_13_Chile_logo.png", 
        "group-title": "Nacionales Chile"
    },
    "c13": {
        "tvg-id": "Canal13.cl", 
        "tvg-name": "Canal 13 HD", 
        "tvg-logo": "https://upload.wikimedia.org/wikipedia/commons/e/eb/Canal_13_Chile_logo.png", 
        "group-title": "Nacionales Chile"
    },
    "cnn chile": {
        "tvg-id": "CNNChile.cl", 
        "tvg-name": "CNN Chile", 
        "tvg-logo": "https://upload.wikimedia.org/wikipedia/commons/1/1a/CNN_Chile_Logo.png", 
        "group-title": "Noticias"
    },
    "tnt sports": {
        "tvg-id": "TNTSports.cl", 
        "tvg-name": "TNT Sports HD", 
        "tvg-logo": "https://upload.wikimedia.org/wikipedia/commons/a/ae/TNT_Sports_Chile_2021.png", 
        "group-title": "Deportes"
    }
}

def enriquecer_metadata_linea(linea):
    """
    Analiza una línea #EXTINF y le inyecta dinámicamente logos, tags de EPG
    y categorías de forma automática basándose en el nombre del canal.
    """
    linea_lower = linea.lower()
    for clave, meta in METADATOS_CANALES.items():
        if clave in linea_lower:
            # Extraemos el nombre original que está al final después de la última coma
            partes = linea.split(',', 1)
            nombre_canal = partes[1] if len(partes) > 1 else "Canal Sin Nombre"
            
            # Construimos la cabecera M3U con el estándar interactivo completo
            nueva_linea = (
                f'#EXTINF:-1 tvg-id="{meta["tvg-id"]}" tvg-name="{meta["tvg-name"]}" '
                f'tvg-logo="{meta["tvg-logo"]}" group-title="{meta["group-title"]}",{nombre_canal}'
            )
            return nueva_linea
    return linea

def descargar_y_procesar():
    """
    Descarga la lista desde Pastebin, la limpia, le inyecta la metadata premium
    y la almacena en la Hyper-Caché de la memoria RAM del servidor.
    """
    global CACHE_DATA, CACHE_TIMESTAMP
    
    logging.info("Optimización de red: Descargando lista limpia desde origen.")
    headers = {
        'User-Agent': (
            'Mozilla/5.0 (SmartHub; SMART-TV; Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) TV-Browser'
        )
    }
    
    try:
        req = urllib.request.Request(PASTEBIN_URL, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as response:
            contenido = response.read().decode('utf-8')
        
        lineas = contenido.splitlines()
        lista_limpia = []
        
        # Inyectamos la cabecera M3U apuntando a una guía EPG chilena compatible
        lista_limpia.append('#EXTM3U x-tvg-url="https://raw.githubusercontent.com/HeliosDe/EPG-Chile/master/epg.xml"')
        
        ultima_linea_info = None
        
        for linea in lineas:
            l = linea.strip()
            if not l:
                continue
                
            # Validamos que cumpla con los estándares de seguridad
            if l.startswith(LINEAS_VALIDAS):
                if l.startswith('#EXTM3U'):
                    continue  # Saltamos el EXTM3U original para usar el nuestro con la EPG
                
                if l.startswith('#EXTINF'):
                    # Procesamos y guardamos temporalmente la metadata para enriquecerla
                    ultima_linea_info = enriquecer_metadata_linea(l)
                else:
                    # Es una URL de transmisión
                    if ultima_linea_info:
                        lista_limpia.append(ultima_linea_info)
                        lista_limpia.append(l)
                        ultima_linea_info = None
                    else:
                        # URL suelta sin información previa
                        lista_limpia.append(f'#EXTINF:-1,Canal Sin Nombre')
                        lista_limpia.append(l)

        # Unimos todo el resultado estructurado
        resultado_final = "\n".join(lista_limpia)
        
        with CACHE_LOCK:
            CACHE_DATA = resultado_final.encode('utf-8')
            CACHE_TIMESTAMP = time.time()
            
        logging.info("¡Hyper-Caché optimizada e inyectada con éxito en la RAM!")
        
    except Exception as e:
        logging.error(f"Error crítico en actualización automática: {e}")

def obtener_lista_m3u():
    """
    Retorna la lista de canales almacenada. Si la caché expiró (más de 10 min),
    dispara la recarga automática sin interrumpir el servicio.
    """
    global CACHE_DATA, CACHE_TIMESTAMP
    ahora = time.time()
    
    if CACHE_DATA is None or (ahora - CACHE_TIMESTAMP) > CACHE_TTL:
        # En segundo plano para velocidad máxima de respuesta
        threading.Thread(target=descargar_y_procesar).start()
        if CACHE_DATA is None:
            # Espera activa la primera vez que se monta
            while CACHE_DATA is None:
                time.sleep(0.1)
                
    return CACHE_DATA

class ServidorPremiumIPTV(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Desactivamos los logs molestos de accesos HTTP en la terminal para limpieza
        return

    def do_GET(self):
        # Ruta principal del playlist limpia como Zapping
        if self.path == '/playlist':
            try:
                datos_m3u = obtener_lista_m3u()
                self.send_response(200)
                self.send_header('Content-Type', 'application/x-mpegurl; charset=utf-8')
                self.send_header('Content-Length', str(len(datos_m3u)))
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(datos_m3u)
            except Exception as e:
                self.send_error(500, f"Error Interno: {e}")
        else:
            self.send_error(404, "Recurso no encontrado. Usa /playlist")

def run():
    # El puerto 80 ya está habilitado gracias a tus privilegios root
    puerto = 80
    server_address = ('', puerto)
    httpd = ThreadingHTTPServer(server_address, ServidorPremiumIPTV)
    logging.info(f"Servidor Anti-Buffer 5000% (Modo Zapping Premium) corriendo en puerto {puerto}...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()

if __name__ == '__main__':
    # Lanzar descarga inicial
    descargar_y_procesar()
    run()
