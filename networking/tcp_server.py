"""
TCP server for Mac AI Brain to handle audio streaming from Raspberry Pi.
Accepts a single client connection for full-duplex raw byte streaming.
"""

import socket
import select
from typing import Optional, Tuple
import threading
from utils.logger import get_logger
logger = get_logger("network", "network.log")


class TCPServer:
    """
    TCP server for raw audio byte streaming with Raspberry Pi.
    
    Features:
    - Single client connection (Phase 1 requirement)
    - Full-duplex byte streaming (receive PCM from Pi, send PCM to Pi)
    - Handles partial sends with sendall()
    - Non-blocking receive with timeout
    - No protocol framing - treats data as opaque bytes
    """
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8888):
        """
        Initialize TCP server without starting.
        
        Args:
            host: IP to bind to (0.0.0.0 for all interfaces)
            port: TCP port for audio streaming
        """
        self.host = host
        self.port = port
        
        self._server_socket: Optional[socket.socket] = None
        self._client_socket: Optional[socket.socket] = None
        self._client_address: Optional[Tuple[str, int]] = None
        
        self._listening = False
        self._connected = False
        
        # Socket timeout for non-blocking recv (very short for real-time)
        self._recv_timeout = 0.001  # 1ms timeout
        # Blocking timeout for accept (5 seconds)
        self._accept_timeout = 5.0
        
        # Lock for thread-safe send operations
        self._send_lock = threading.Lock()
        
    def start(self) -> None:
        """
        Start TCP server and begin listening for connections.
        
        Raises:
            OSError: If server cannot bind to port
            socket.error: For socket-related errors
        """
        if self._listening:
            return
            
        try:
            # Create TCP socket
            self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # Bind to host and port
            self._server_socket.bind((self.host, self.port))
            
            # Listen for single connection (Phase 1)
            self._server_socket.listen(1)
            self._listening = True
            
        except socket.error as e:
            self._cleanup_server_socket()
            logger.error(f"Failed to start server on {self.host}:{self.port}")
            raise

    
    def accept(self, timeout: Optional[float] = None) -> Tuple[str, int]:
        """
        Accept a client connection (blocks until client connects).
        
        Args:
            timeout: Seconds to wait for connection (None = indefinite)
            
        Returns:
            Tuple of (client_ip, client_port)
            
        Raises:
            TimeoutError: If timeout occurs while waiting for connection
            socket.error: For socket-related errors
            RuntimeError: If server not listening or already connected
        """
        if not self._listening:
            raise RuntimeError("Server must be started before accepting connections")
        
        if self._connected:
            raise RuntimeError("Server already has a connected client")
        
        try:
            # Set timeout for accept
            original_timeout = self._server_socket.gettimeout()
            self._server_socket.settimeout(timeout or self._accept_timeout)
            
            # Accept client connection
            client_socket, client_address = self._server_socket.accept()
            
            # Restore original timeout
            self._server_socket.settimeout(original_timeout)
            
            # Configure client socket for real-time audio
            client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            client_socket.settimeout(self._recv_timeout)
            
            # Store client information
            self._client_socket = client_socket
            self._client_address = client_address
            self._connected = True
            
            return client_address
            
        except socket.timeout:
            raise TimeoutError(f"No client connection within {timeout or self._accept_timeout}s")
        except socket.error as e:
            self._cleanup_client_socket()
            raise socket.error(f"Failed to accept client: {str(e)}")
    
    def send(self, data: bytes) -> None:
        """
        Send raw bytes to connected client.
        
        Uses sendall() to handle partial sends automatically.
        Thread-safe and prevents deadlock from slow clients.
        
        Args:
            data: Raw bytes to send (PCM audio chunks)
            
        Raises:
            ConnectionError: If no client connected or connection broken
            socket.error: For socket-related errors
        """
        if not self._connected or not self._client_socket:
            raise ConnectionError("No client connected")
        
        with self._send_lock:
            try:
                # Simplified: direct sendall without blocking mode toggling
                self._client_socket.sendall(data)
                    
            except socket.error as e:
                self._cleanup_client_socket()
                raise ConnectionError(f"Send failed: {str(e)}")
    
    def receive(self, max_bytes: int = 4096) -> Optional[bytes]:
        """
        Receive raw bytes from connected client.
        
        Non-blocking check with timeout to avoid indefinite blocking.
        Never blocks the calling thread.
        
        Args:
            max_bytes: Maximum bytes to receive in one call
            
        Returns:
            bytes: Received data, or None if no data available
            
        Raises:
            ConnectionError: If connection broken during receive
            socket.timeout: If timeout occurs (normal for non-blocking)
        """
        if not self._connected or not self._client_socket:
            raise ConnectionError("No client connected")
        
        try:
            # Use select to check if data is available (non-blocking)
            # timeout=0 means we don't block waiting for data
            ready, _, _ = select.select([self._client_socket], [], [], 0)
            if not ready:
                return None
                
            # Receive available data (won't block due to select check)
            data = self._client_socket.recv(max_bytes)
            if not data:
                # Empty data indicates graceful connection close from client
                self._cleanup_client_socket()
                raise ConnectionError("Client closed connection")
                
            return data
            
        except socket.timeout:
            # Timeout is expected in non-blocking mode
            return None
        except socket.error as e:
            self._cleanup_client_socket()
            raise ConnectionError(f"Receive failed: {str(e)}")
    
    def close_client(self) -> None:
        """Close client connection but keep server listening."""
        self._cleanup_client_socket()
    
    def close(self) -> None:
        """Close client connection and stop server."""
        self._cleanup_client_socket()
        self._cleanup_server_socket()
        self._listening = False
    
    def is_listening(self) -> bool:
        """Check if server is currently listening."""
        return self._listening
    
    def is_connected(self) -> bool:
        """Check if server has a connected client."""
        return self._connected
    
    def get_client_address(self) -> Optional[Tuple[str, int]]:
        """Get address of connected client."""
        return self._client_address
    
    def _cleanup_client_socket(self) -> None:
        """Clean up client socket and connection state."""
        with self._send_lock:  # Acquire lock before closing socket
            if self._client_socket:
                try:
                    # Shutdown and close socket without flushing
                    self._client_socket.shutdown(socket.SHUT_RDWR)
                except (socket.error, OSError):
                    pass
                finally:
                    self._client_socket.close()
            
            self._client_socket = None
            self._client_address = None
            self._connected = False
    
    def _cleanup_server_socket(self) -> None:
        """Clean up server socket."""
        if self._server_socket:
            try:
                self._server_socket.shutdown(socket.SHUT_RDWR)
            except (socket.error, OSError):
                pass
            finally:
                self._server_socket.close()
        
        self._server_socket = None
    
    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensures cleanup."""
        self.close()
    
    def __del__(self):
        """Destructor ensures sockets are closed."""
        try:
            self.close()
        except (AttributeError, TypeError):
            # Ignore errors during interpreter shutdown
            pass


# Optional: Factory function for convenience
def create_tcp_server(host: str = "0.0.0.0", port: int = 8888) -> TCPServer:
    """
    Create a configured TCP server.
    
    Args:
        host: IP to bind to
        port: TCP port for audio streaming
        
    Returns:
        TCPServer: Configured server instance
    """
    return TCPServer(host, port)
