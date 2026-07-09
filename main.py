#-*-coding:utf8;-*-
import http.server
import socketserver
import urllib.request
import urllib.error
import urllib.parse
import http.client
import threading
import time
import socket
import sys
import os

# =====================================================================
# CONFIGURACIÓN CENTRALIZADA
# =====================================================================
CONFIG = {
    "PORT": 8080,
    # Tu lista de canales de Pastebin ya integrada:
    "PASTEBIN_URL": "https://pastebin.com/raw/Q5V2s2Rd", 

    "BUFFER_CAPACITY_BYTES": 20 * 1024 * 1024,
    "CHUNK_SIZE": 188 * 96,        
    "SEND_BATCH_SIZE": 188 * 192,  

    "BUFFER_MIN_SECONDS": 3.0,      
    "BUFFER_TARGET_SECONDS": 8.0,   
    "BUFFER_MAX_SECONDS": 20.0,     
    "BUFFER_START_SECONDS": 1.2,    
    "MAX_INITIAL_WAIT": 4.0,        

    "WATCHDOG_POLL_INTERVAL": 0.3,
    "STALL_TIMEOUT_MIN": 2.5,   
    "STALL_TIMEOUT_MAX": 10.0,  
    "RECONNECT_COOLDOWN": 4.0,  

    "MAX_PACING_SLEEP": 0.4,  

    "UPSTREAM_CONNECT_TIMEOUT": 5.0,
    "MAX_RECONNECT_ATTEMPTS": 15,
    "BASE_RECONNECT_DELAY": 0.4,
    "MAX_RECONNECT_DELAY": 6.0,

    "TRANSFER_MODE": "continuous",
    "SHOW_STATS": True,
    "STATS_INTERVAL": 2.0,
}

class PreallocatedCircularBuffer:
    def __init__(self, capacity):
        self.buffer = bytearray(capacity)
        self.capacity = capacity
        self.head = 0
        self.tail = 0
        self.size = 0
        self.lock = threading.Lock()
        self.not_empty = threading.Condition(self.lock)

    def write(self, data):
        with self.lock:
            length = len(data)
            if self.size + length > self.capacity:
                return False  
            right_space = self.capacity - self.head
            if length <= right_space:
                self.buffer[self.head:self.head + length] = data
            else:
                self.buffer[self.head:self.capacity] = data[:right_space]
                self.buffer[0:length - right_space] = data[right_space:]
            self.head = (self.head + length) % self.capacity
            self.size += length
            self.not_empty.notify_all()
            return True

    def read(self, max_bytes):
        with self.lock:
            if self.size == 0:
                return b""
            to_read = min(max_bytes, self.size)
            right_space = self.capacity - self.tail
            if to_read <= right_space:
                data = self.buffer[self.tail:self.tail + to_read]
            else:
                data = self.buffer[self.tail:self.capacity] + self.buffer[0:to_read - right_space]
            self.tail = (self.tail + to_read) % self.capacity
            self.size -= to_read
            return data

    def clear(self):
        with self.lock:
            self.head = 0
            self.tail = 0
            self.size = 0

class AdaptiveBufferManager:
    def __init__(self):
        self.lock = threading.Lock()
        self.target_seconds = CONFIG["BUFFER_TARGET_SECONDS"]
        self.last_incident = time.time()

    def notify_incident(self):
        with self.lock:
            self.last_incident = time.time()
            self.target_seconds = min(CONFIG["BUFFER_MAX_SECONDS"], self.target_seconds + 2.0)

    def get_target_seconds(self):
        with self.lock:
            if (time.time() - self.last_incident > 60.0
                    and self.target_seconds > CONFIG["BUFFER_TARGET_SECONDS"]):
                self.target_seconds = max(CONFIG["BUFFER_TARGET_SECONDS"], self.target_seconds - 0.5)
                self.last_incident = time.time()
            return self.target_seconds

class TelemetryCore:
    def __init__(self, url):
        self.url = url
        self.start_time = time.time()
        self.bytes_received = 0
        self.bytes_sent = 0
        self.reconnections = 0
        self.status = "Iniciando pipeline"
        self.stream_type = "MPEG-TS / HLS"
        self.smoothed_bitrate = 0.0
        self.lock = threading.Lock()

    def update_bitrate(self, instant_bytes, delta_time):
        if delta_time <= 0:
            return
        instant_bitrate = (instant_bytes * 8) / delta_time
        with self.lock:
            if self.smoothed_bitrate == 0.0:
                self.smoothed_bitrate = instant_bitrate
            else:
                self.smoothed_bitrate = (0.8 * self.smoothed_bitrate) + (0.2 * instant_bitrate)

    def get_buffer_seconds(self, current_buffer_bytes):
        with self.lock:
            bitrate = self.smoothed_bitrate
        if bitrate <= 0:
            return 0.0
        return current_buffer_bytes / (bitrate / 8)

    def draw_dashboard(self, current_buffer_bytes, buffer_capacity, target_seconds):
        if not CONFIG["SHOW_STATS"]:
            return
        elapsed = time.time() - self.start_time
        speed_in = (self.bytes_received / 1024) / elapsed if elapsed > 0 else 0
        speed_out = (self.bytes_sent / 1024) / elapsed if elapsed > 0 else 0
        buffer_seconds = self.get_buffer_seconds(current_buffer_bytes)

        lines = (
            "=================================================================\n"
            "  AUDITORÍA CORE IPTV PROXY - TELEMETRÍA DE RED (v6.1-Cloud)\n"
            "=================================================================\n"
            f"[-] Canal Origen  : {self.url[:55]}...\n"
            f"[-] Tipo Stream   : {self.stream_type} | Estado: {self.status}\n"
            f"[-] Tiempo Flujo  : {elapsed:.1f}s | Reconexiones: {self.reconnections}\n"
            f"[-] Bitrate (EMA) : {self.smoothed_bitrate / 1000:.1f} kbps\n"
            f"[-] Velocidad Red : IN: {speed_in:.1f} KB/s | OUT: {speed_out:.1f} KB/s\n"
            f"[-] Búfer Físico  : {current_buffer_bytes / 1024:.1f} KB / {buffer_capacity / 1024:.1f} KB\n"
            f"[-] Colchón Real  : {buffer_seconds:.2f}s (objetivo adaptativo: {target_seconds:.1f}s)\n"
            f"[-] Modo Transfer : {CONFIG['TRANSFER_MODE']}\n"
            "=================================================================\n"
        )
        sys.stdout.write("\033[H\033[J" + lines)
        sys.stdout.flush()

class SharedTimestamp:
    __slots__ = ("_lock", "_value")
    def __init__(self):
        self._lock = threading.Lock()
        self._value = time.time()
    def touch(self):
        with self._lock:
            self._value = time.time()
    def elapsed(self):
        with self._lock:
            return time.time() - self._value

class ConnectionState:
    def __init__(self):
        self.lock = threading.Lock()
        self.response = None
    def set_active(self, response):
        with self.lock:
            self.response = response
    def clear_if(self, response):
        with self.lock:
            if self.response is response:
                self.response = None
    def force_close_if_stale(self, timestamp, stall_timeout):
        with self.lock:
            if self.response is None:
                return False
            if timestamp.elapsed() <= stall_timeout:
                return False
            try:
                self.response.close()
            except Exception:
                pass
            return True

def compute_dynamic_stall_timeout(buffer_seconds, target_seconds):
    if target_seconds <= 0:
        return CONFIG["STALL_TIMEOUT_MIN"]
    ratio = max(0.0, min(1.0, buffer_seconds / target_seconds))
    return CONFIG["STALL_TIMEOUT_MIN"] + ratio * (CONFIG["STALL_TIMEOUT_MAX"] - CONFIG["STALL_TIMEOUT_MIN"])

class CustomThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    def server_bind(self):
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass
        super().server_bind()

class CoreProxyHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass
    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-Type', 'video/mp2t')
        self.send_header('Connection', 'close')
        self.end_headers()
    def do_GET(self):
        if self.path == "/" or self.path == "/playlist.m3u":
            self._serve_playlist()
            return
        if self.path.startswith("/stream"):
            self._serve_stream()
            return
        self.send_error(404, "Ruta no encontrada")

    def _serve_playlist(self):
        try:
            req = urllib.request.Request(
                CONFIG["PASTEBIN_URL"], headers={'User-Agent': 'IPTV-CoreProxy/6.1'}
            )
            with urllib.request.urlopen(req, timeout=CONFIG["UPSTREAM_CONNECT_TIMEOUT"]) as response:
                content = response.read().decode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/vnd.apple.mpegurl')
            self.send_header('Connection', 'close')
            self.end_headers()
            host = self.headers.get('Host', f'127.0.0.1:{CONFIG["PORT"]}')
            modified = []
            for line in content.splitlines():
                clean_line = line.strip()
                if clean_line.startswith("http://") or clean_line.startswith("https://"):
                    modified.append(f"http://{host}/stream?url={urllib.parse.quote(clean_line)}")
                else:
                    modified.append(clean_line)
            self.wfile.write("\n".join(modified).encode('utf-8'))
        except Exception as e:
            self.send_error(502, f"Error de Gateway M3U: {e}")

    def _serve_stream(self):
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        if 'url' not in params:
            self.send_error(400, "Parámetro URL faltante")
            return
        stream_url = params['url'][0]
        parsed = urllib.parse.urlparse(stream_url)
        if parsed.scheme not in ("http", "https"):
            self.send_error(400, "Esquema no permitido")
            return

        circ_buffer = PreallocatedCircularBuffer(CONFIG["BUFFER_CAPACITY_BYTES"])
        telemetry = TelemetryCore(stream_url)
        conn_state = ConnectionState()
        buffer_mgr = AdaptiveBufferManager()
        stop_event = threading.Event()
        last_data = SharedTimestamp()

        def producer_pipeline():
            attempt = 0
            while not stop_event.is_set() and attempt < CONFIG["MAX_RECONNECT_ATTEMPTS"]:
                response = None
                try:
                    telemetry.status = "Conectando" if attempt == 0 else f"Recon. (intento {attempt})"
                    req = urllib.request.Request(stream_url, headers={'User-Agent': 'VLC/3.0.18 LibVLC/3.0.18'})
                    response = urllib.request.urlopen(req, timeout=CONFIG["UPSTREAM_CONNECT_TIMEOUT"])
                    conn_state.set_active(response)
                    last_data.touch()
                    telemetry.status = "Recibiendo datos"
                    c_type = response.headers.get('Content-Type', '').lower()
                    if "m3u8" in stream_url or "mpegurl" in c_type:
                        telemetry.stream_type = "HLS"
                    else:
                        telemetry.stream_type = "MPEG-TS"
                    measure_start = time.time()
                    bytes_bucket = 0
                    got_first_byte = False
                    while not stop_event.is_set():
                        chunk = response.read(CONFIG["CHUNK_SIZE"])
                        now = time.time()
                        last_data.touch()
                        if not chunk:
                            break
                        if not got_first_byte:
                            attempt = 0
                            got_first_byte = True
                        if circ_buffer.write(chunk):
                            telemetry.bytes_received += len(chunk)
                            bytes_bucket += len(chunk)
                        delta = now - measure_start
                        if delta >= 1.0:
                            telemetry.update_bitrate(bytes_bucket, delta)
                            bytes_bucket = 0
                            measure_start = now
                except Exception as e:
                    if stop_event.is_set():
                        return
                    attempt += 1
                    telemetry.reconnections += 1
                    telemetry.status = f"Corte: {e}"
                    buffer_mgr.notify_incident()
                    time.sleep(min(CONFIG["BASE_RECONNECT_DELAY"] * (2 ** (attempt - 1)), CONFIG["MAX_RECONNECT_DELAY"]))
                finally:
                    conn_state.clear_if(response)
                    if response is not None:
                        try: response.close()
                        except: pass
            stop_event.set()

        def watchdog_pipeline():
            last_forced_close = 0.0
            while not stop_event.is_set():
                time.sleep(CONFIG["WATCHDOG_POLL_INTERVAL"])
                if time.time() - last_forced_close < CONFIG["RECONNECT_COOLDOWN"]:
                    continue
                buffer_seconds = telemetry.get_buffer_seconds(circ_buffer.size)
                dynamic_timeout = compute_dynamic_stall_timeout(buffer_seconds, buffer_mgr.get_target_seconds())
                if conn_state.force_close_if_stale(last_data, dynamic_timeout):
                    last_forced_close = time.time()
                    buffer_mgr.notify_incident()

        if CONFIG["SHOW_STATS"]:
            def ui_pipeline():
                while not stop_event.is_set():
                    telemetry.draw_dashboard(circ_buffer.size, CONFIG["BUFFER_CAPACITY_BYTES"], buffer_mgr.get_target_seconds())
                    time.sleep(CONFIG["STATS_INTERVAL"])
            threading.Thread(target=ui_pipeline, daemon=True).start()

        t_prod = threading.Thread(target=producer_pipeline, daemon=True)
        t_watch = threading.Thread(target=watchdog_pipeline, daemon=True)
        t_prod.start()
        t_watch.start()

        try:
            self._send_stream_headers()
            self._consume_and_send(circ_buffer, telemetry, stop_event, buffer_mgr)
        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            stop_event.set()
            circ_buffer.clear()

    def _send_stream_headers(self):
        self.protocol_version = 'HTTP/1.1'
        self.send_response(200)
        self.send_header('Content-Type', 'video/mp2t')
        self.send_header('Cache-Control', 'no-cache')
        self.close_connection = True
        self.send_header('Connection', 'close')
        self.end_headers()

    def _consume_and_send(self, circ_buffer, telemetry, stop_event, buffer_mgr):
        initial_buffer_filled = False
        wait_start = time.time()
        playout_clock_start = time.time()
        bytes_sent_since_clock = 0
        while not stop_event.is_set() or circ_buffer.size > 0:
            with circ_buffer.lock:
                if not initial_buffer_filled:
                    reached_start = telemetry.get_buffer_seconds(circ_buffer.size) >= CONFIG["BUFFER_START_SECONDS"]
                    timed_out = (time.time() - wait_start) > CONFIG["MAX_INITIAL_WAIT"]
                    circ_buffer.not_empty.wait_for(lambda: reached_start or stop_event.is_set() or timed_out, timeout=0.2)
                    if reached_start or stop_event.is_set() or timed_out:
                        initial_buffer_filled = True
                else:
                    circ_buffer.not_empty.wait_for(lambda: circ_buffer.size > 0 or stop_event.is_set(), timeout=0.2)

            data_to_send = circ_buffer.read(CONFIG["SEND_BATCH_SIZE"])
            if data_to_send:
                chunk_len = len(data_to_send)
                bitrate = telemetry.smoothed_bitrate
                if bitrate > 0:
                    bytes_per_second = bitrate / 8.0
                    allowed_bytes = (bytes_per_second * (time.time() - playout_clock_start)) + (bytes_per_second * buffer_mgr.get_target_seconds())
                    if bytes_sent_since_clock + chunk_len > allowed_bytes:
                        time.sleep(min((bytes_sent_since_clock + chunk_len - allowed_bytes) / bytes_per_second, CONFIG["MAX_PACING_SLEEP"]))
                self.wfile.write(data_to_send)
                self.wfile.flush()
                telemetry.bytes_sent += chunk_len
                bytes_sent_since_clock += chunk_len
            else:
                if stop_event.is_set() and circ_buffer.size == 0:
                    break

if __name__ == "__main__":
    cloud_port = int(os.environ.get("PORT", CONFIG["PORT"]))
    server = CustomThreadedHTTPServer(('0.0.0.0', cloud_port), CoreProxyHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
