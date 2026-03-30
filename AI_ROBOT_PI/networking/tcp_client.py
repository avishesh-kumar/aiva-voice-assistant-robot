"""
TCP client for full-duplex audio streaming between Raspberry Pi and Mac AI Brain.
Handles raw PCM byte streaming without protocol framing.
"""

import socket
import select
from typing import Optional, Tuple
from config.network_config import MAC_HOST


class TCPClient:
    """
    TCP client for streaming raw audio bytes to/from Mac AI Brain.
    
    Features:
    - Full-duplex byte streaming (send PCM from mic, receive PCM for speaker)
    - Handles partial sends with sendall()
    - Non-blocking receive with timeout
    - No protocol framing - treats data as opaque bytes
    """
    
    def __init__(self, host: str = MAC_HOST, port: int = 8888):
        """
        Initialize TCP client without connecting.
        
        Args:
            host: Mac AI Brain IP address
            port: TCP port for audio streaming
        """
        self.host = host
        self.port = port
        self._socket: Optional[socket.socket] = None
        self._connected = False
        
        # Socket timeout for non-blocking recv (1 second)
        self._recv_timeout = 1.0
        
    def connect(self) -> None:
        """
        Establish TCP connection to Mac AI Brain.
        
        Raises:
            ConnectionError: If connection fails
            socket.error: For socket-related errors
        """
        if self._connected:
            return
            
        try:
            # Create TCP socket
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # Set timeout for recv operations
            self._socket.settimeout(self._recv_timeout)
            
            # Connect to server
            self._socket.connect((self.host, self.port))
            self._connected = True
            
        except socket.error as e:
            self._cleanup_socket()
            raise ConnectionError(f"Failed to connect to {self.host}:{self.port}: {str(e)}")
    
    def send(self, data: bytes) -> None:
        """
        Send raw bytes to Mac AI Brain.
        
        Uses sendall() to handle partial sends automatically.
        
        Args:
            data: Raw bytes to send (PCM audio chunks)
            
        Raises:
            ConnectionError: If not connected or connection broken
            socket.error: For socket-related errors
        """
        if not self._connected or not self._socket:
            return False
        
        try:
            # sendall() ensures all bytes are sent, handling partial sends
            self._socket.sendall(data)
            return True
        except (socket.timeout, BlockingIOError):
            return False
        except socket.error as e:
            self._close_connection()
            raise ConnectionError(f"Send failed: {str(e)}")

    def receive(self, max_bytes: int = 4096) -> Optional[bytes]:
        """
        Receive raw bytes from Mac AI Brain.
        
        Uses non-blocking check with timeout to avoid indefinite blocking.
        
        Args:
            max_bytes: Maximum bytes to receive in one call
            
        Returns:
            bytes: Received data, or None if no data available
            
        Raises:
            ConnectionError: If connection broken during receive
            socket.timeout: If timeout occurs (normal for non-blocking)
        """
        if not self._connected or not self._socket:
            raise ConnectionError("Not connected to server")
        
        try:
            # Use select to check if data is available (non-blocking)
            ready, _, _ = select.select([self._socket], [], [], 0)
            if not ready:
                return None
                
            # Receive available data
            data = self._socket.recv(max_bytes)
            if not data:
                # Empty data indicates graceful connection close from server
                self._close_connection()
                raise ConnectionError("Server closed connection")
                
            return data
            
        except socket.timeout:
            # Timeout is expected in non-blocking mode
            return None
        except socket.error as e:
            self._close_connection()
            raise ConnectionError(f"Receive failed: {str(e)}")
    
    def close(self) -> None:
        """Gracefully close TCP connection."""
        self._close_connection()
    
    def is_connected(self) -> bool:
        """Check if client is currently connected."""
        return self._connected
    
    def _close_connection(self) -> None:
        """Internal method to close socket and update state."""
        if self._socket:
            try:
                self._socket.shutdown(socket.SHUT_RDWR)
            except (socket.error, OSError):
                pass
            finally:
                self._socket.close()
        
        self._cleanup_socket()
        self._connected = False
    
    def _cleanup_socket(self) -> None:
        """Clean up socket reference."""
        self._socket = None
    
    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensures cleanup."""
        self.close()
    
    def __del__(self):
        """Destructor ensures connection is closed."""
        try:
            self.close()
        except (AttributeError, TypeError):
            # Ignore errors during interpreter shutdown
            pass


# Optional: Factory function for convenience
def create_tcp_client(host: str = MAC_HOST, port: int = 8888) -> TCPClient:
    """
    Create a configured TCP client.
    
    Args:
        host: Mac AI Brain IP address
        port: TCP port for audio streaming
        
    Returns:
        TCPClient: Configured client instance
    """
    return TCPClient(host, port)
