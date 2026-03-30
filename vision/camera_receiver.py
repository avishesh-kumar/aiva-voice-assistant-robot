# vision/camera_receiver.py
import socket
import struct
import time
import threading
import numpy as np
import cv2

class CameraReceiver:
    def __init__(self, host="0.0.0.0", port=8891):
        self.host = host
        self.port = port
        
        self.running = False
        self.server_socket = None
        self.client_socket = None
        self.client_address = None
        
        self.receive_thread = None
        
        # Frame buffer attributes
        self.latest_frame = None
        self.latest_jpeg = None
        self.last_frame_time = 0.0
        self.frames_received = 0
        
        self.frame_count = 0
        self.last_fps_time = time.time()
        
    def _setup_socket(self):
        """Setup server socket"""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.settimeout(2.0)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(1)
        print(f"[VISION] Server listening on {self.host}:{self.port}")
    
    def _accept_client(self):
        """Wait for client connection"""
        while self.running:
            try:
                client_socket, client_address = self.server_socket.accept()
                client_socket.settimeout(2.0)
                self.client_socket = client_socket
                self.client_address = client_address
                print(f"[VISION] Client connected: {client_address}")
                return True
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"[VISION] Accept error: {e}, retrying...")
                continue
        return False
    
    def _recv_exact(self, n):
        """Receive exactly n bytes from socket"""
        data = b''
        while len(data) < n and self.running:
            try:
                chunk = self.client_socket.recv(n - len(data))
                if not chunk:
                    raise ConnectionError("Connection closed")
                data += chunk
            except socket.timeout:
                continue
            except Exception as e:
                raise ConnectionError(f"Receive error: {e}")
        return data
    
    def _recv_frame(self):
        """Receive a single frame (4-byte length + jpeg data)"""
        length_bytes = self._recv_exact(4)
        if len(length_bytes) != 4:
            raise ConnectionError("Failed to read length prefix")
        
        frame_length = struct.unpack(">I", length_bytes)[0]
        jpeg_bytes = self._recv_exact(frame_length)
        
        return jpeg_bytes
    
    def _decode_jpeg(self, jpeg_bytes):
        """Decode JPEG bytes to numpy array"""
        try:
            frame = cv2.imdecode(
                np.frombuffer(jpeg_bytes, dtype=np.uint8),
                cv2.IMREAD_COLOR
            )

            # 🔒 HARD GUARANTEES FOR DISPLAY
            if frame is not None:
                frame = frame.astype(np.uint8)
                frame = np.ascontiguousarray(frame)
            return frame
        except Exception as e:
            print(f"[VISION] Decode error: {e}")
            return None
    
    def _calculate_fps(self):
        """Calculate and print FPS"""
        self.frame_count += 1
        current_time = time.time()
        elapsed = current_time - self.last_fps_time
        
        if elapsed >= 5.0:
            fps = self.frame_count / elapsed
            print(f"[VISION] FPS: {fps:.1f}, Total frames: {self.frame_count}")
            self.frame_count = 0
            self.last_fps_time = current_time
    
    def _receive_loop(self):
        """Main receive loop"""
        while self.running:
            try:
                if self.client_socket is None:
                    if not self._accept_client():
                        continue
                
                jpeg_bytes = self._recv_frame()
                
                frame = self._decode_jpeg(jpeg_bytes)
                
                if frame is not None:
                    # Update frame buffer
                    self.latest_frame = frame
                    self.latest_jpeg = jpeg_bytes
                    self.last_frame_time = time.time()
                    self.frames_received += 1
                
                self._calculate_fps()
                
            except ConnectionError as e:
                print(f"[VISION] Connection error: {e}")
                self._close_client()
                time.sleep(1)
            except Exception as e:
                if self.running:
                    print(f"[VISION] Unexpected error in receive loop: {e}")
                    self._close_client()
                    time.sleep(1)
    
    def _close_client(self):
        """Close client connection"""
        if self.client_socket:
            try:
                self.client_socket.close()
            except:
                pass
            self.client_socket = None
            self.client_address = None
            print("[VISION] Client disconnected")
    
    def get_latest_frame(self):
        """Get the latest frame and its timestamp"""
        return self.latest_frame, self.last_frame_time
    
    def start(self):
        """Start the camera receiver"""
        if self.running:
            return
        
        print(f"[VISION] Starting camera receiver on {self.host}:{self.port}")
        self.running = True
        
        self._setup_socket()
        
        self.receive_thread = threading.Thread(target=self._receive_loop)
        self.receive_thread.daemon = True
        self.receive_thread.start()
        
        print("[VISION] Camera receiver started")
    
    def stop(self):
        """Stop the camera receiver"""
        if not self.running:
            return
        
        print("[VISION] Stopping camera receiver...")
        self.running = False
        
        self._close_client()
        
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
            self.server_socket = None
        
        if self.receive_thread and self.receive_thread.is_alive():
            self.receive_thread.join(timeout=2.0)
        
        print("[VISION] Camera receiver stopped")
