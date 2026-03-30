# camera/camera_stream.py
import socket
import time
import struct
import threading
import subprocess
import os
from config.network_config import MAC_HOST

try:
    import yaml
except ImportError:
    yaml = None


class CameraStreamer:
    def __init__(self, host, port, fps=15, jpeg_quality=70, width=640, height=480):
        self.host = host
        self.port = port
        self.fps = fps
        self.jpeg_quality = jpeg_quality
        self.width = width
        self.height = height

        self.running = False
        self.client_socket = None
        self.stream_thread = None

        print(f"[CAMERA] Using rpicam-vid ({width}x{height} @ {fps} FPS)")

    # -------------------------------------------------
    # Socket utilities
    # -------------------------------------------------

    def _create_socket(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        return sock

    def _connect(self):
        while self.running:
            try:
                self.client_socket = self._create_socket()
                self.client_socket.settimeout(5.0)
                self.client_socket.connect((self.host, self.port))
                self.client_socket.settimeout(None)
                print(f"[CAMERA] Connected to {self.host}:{self.port}")
                return True

            except Exception as e:
                print(f"[CAMERA] Connection error: {e}")
                self._safe_close_socket()
                time.sleep(2)

        return False

    def _safe_close_socket(self):
        if self.client_socket:
            try:
                self.client_socket.shutdown(socket.SHUT_RDWR)
            except:
                pass
            try:
                self.client_socket.close()
            except:
                pass
            self.client_socket = None

    # -------------------------------------------------
    # Networking
    # -------------------------------------------------

    def _send_frame(self, jpeg_bytes):
        if not jpeg_bytes or self.client_socket is None:
            return False

        try:
            frame_data = struct.pack(">I", len(jpeg_bytes)) + jpeg_bytes
            self.client_socket.sendall(frame_data)
            return True

        except Exception as e:
            print(f"[CAMERA] Send error: {e}")
            self._safe_close_socket()
            return False

    # -------------------------------------------------
    # Main streaming loop
    # -------------------------------------------------

    def _stream_loop(self):
        """Continuous MJPEG stream using rpicam-vid"""

        while self.running:
            if self.client_socket is None:
                if not self._connect():
                    time.sleep(1)
                    continue

            process = None

            try:
                cmd = [
                    "rpicam-vid",
                    "-t", "0",

                    "--width", str(self.width),
                    "--height", str(self.height),
                    "--framerate", str(self.fps),

                    "--exposure", "normal",
                    "--awb", "indoor",  
                    "--gain", "6.0",
                    "--shutter", "70000",

                    "--codec", "mjpeg",
                    "--nopreview",
                    "-o", "-"
                ]

                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    bufsize=0
                )

                buffer = b""

                while self.running:
                    chunk = process.stdout.read(4096)
                    if not chunk:
                        break

                    buffer += chunk

                    # FIXED MJPEG FRAME EXTRACTION
                    while True:
                        start = buffer.find(b"\xff\xd8")
                        if start == -1:
                            break

                        end = buffer.find(b"\xff\xd9", start + 2)
                        if end == -1:
                            break

                        frame = buffer[start:end + 2]
                        buffer = buffer[end + 2:]

                        # Drop obviously invalid frames
                        if len(frame) < 100:
                            continue

                        if not self._send_frame(frame):
                            raise ConnectionError("Send failed")

            except Exception as e:
                print(f"[CAMERA] Stream error: {e}")
                time.sleep(1)

            finally:
                if process:
                    try:
                        process.kill()
                    except:
                        pass

    # -------------------------------------------------
    # Public API
    # -------------------------------------------------

    def start(self):
        if self.running:
            return

        print(f"[CAMERA] Starting stream to {self.host}:{self.port}")
        self.running = True

        self.stream_thread = threading.Thread(target=self._stream_loop, daemon=True)
        self.stream_thread.start()

        print("[CAMERA] Camera streaming started")

    def stop(self):
        if not self.running:
            return

        print("[CAMERA] Stopping camera streaming...")
        self.running = False

        if self.stream_thread and self.stream_thread.is_alive():
            self.stream_thread.join(timeout=2.0)

        self._safe_close_socket()
        print("[CAMERA] Camera streaming stopped")


# -------------------------------------------------
# Config loader
# -------------------------------------------------

def load_network_config():
    default_host = MAC_HOST
    default_port = 8891

    config_path = "config/network_config.yaml"

    if not os.path.exists(config_path):
        print(f"[CAMERA] Config file not found: {config_path}, using defaults")
        return default_host, default_port

    if yaml is None:
        print("[CAMERA] PyYAML not installed, using defaults")
        return default_host, default_port

    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f) or {}

        host = config.get("camera_host", default_host)
        port = config.get("camera_port", default_port)

        print(f"[CAMERA] Loaded config: {host}:{port}")
        return host, port

    except Exception as e:
        print(f"[CAMERA] Error loading config: {e}, using defaults")
        return default_host, default_port
