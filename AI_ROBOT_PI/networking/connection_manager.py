"""
Connection manager for TCP client with auto-reconnect logic.
Manages lifecycle and connection state for audio streaming.
"""

import time
import threading
from typing import Optional
from config.network_config import MAC_HOST, AUDIO_PORT

# Import from the tcp_client module we're managing
from networking.tcp_client import TCPClient


class ConnectionManager:
    """
    Manages TCP client connection with auto-reconnect capability.
    
    Provides:
    - Connection lifecycle management
    - Automatic reconnection on failure
    - Connection state monitoring
    """
    
    def __init__(self, client: TCPClient, retry_delay: float = 3.0):
        """
        Initialize connection manager.
        
        Args:
            client: TCPClient instance to manage
            retry_delay: Seconds between reconnection attempts (2-5 seconds range)
        """
        self.client = client
        self.retry_delay = max(2.0, min(5.0, retry_delay))  # Clamp to 2-5 seconds
        
        self._running = False
        self._reconnect_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._connection_lock = threading.Lock()
        
        # Connection state tracking
        self._is_connected = False
        self._last_connection_attempt: Optional[float] = None
        
    def start(self) -> None:
        """
        Start connection management with auto-reconnect.
        
        Starts background thread to monitor and maintain connection.
        """
        if self._running:
            return
            
        self._running = True
        self._stop_event.clear()
        
        # Start reconnect thread
        self._reconnect_thread = threading.Thread(
            target=self._reconnect_loop,
            name="ConnectionManager",
            daemon=True  # Allows program to exit even if thread is running
        )
        self._reconnect_thread.start()
        
    def stop(self) -> None:
        """
        Stop connection management and close connection.
        
        Stops reconnect thread and ensures client is closed.
        """
        if not self._running:
            return
            
        self._running = False
        self._stop_event.set()
        
        # Close client connection
        with self._connection_lock:
            self.client.close()
            self._is_connected = False
        
        # Wait for thread to complete (with timeout to avoid blocking indefinitely)
        if self._reconnect_thread and self._reconnect_thread.is_alive():
            self._reconnect_thread.join(timeout=2.0)
    def _reconnect_loop(self) -> None:
        """
        Main reconnection loop running in background thread.
        
        Continuously attempts to establish/maintain TCP connection.
        """
        while self._running and not self._stop_event.is_set():
            try:
                # Check current connection status
                with self._connection_lock:
                    is_connected = self.client.is_connected()
                    self._is_connected = is_connected
                
                # If disconnected, attempt to reconnect
                if not is_connected:
                    self._attempt_reconnect()
                
                # Wait before next check (or until stopped)
                self._stop_event.wait(timeout=self.retry_delay)
                
            except Exception:
                # Catch all exceptions to prevent thread crash
                # Wait before retrying after any error
                self._stop_event.wait(timeout=self.retry_delay)
    
    def _attempt_reconnect(self) -> None:
        """
        Attempt a single reconnection attempt.
        
        Handles connection attempt with proper error handling.
        """
        try:
            self._last_connection_attempt = time.time()
            
            with self._connection_lock:
                # Ensure client is fully closed before reconnecting
                self.client.close()
                
                # Attempt new connection
                self.client.connect()
                self._is_connected = True
                
        except (ConnectionError, OSError, TimeoutError) as e:
            # Connection failed - expected during reconnection attempts
            with self._connection_lock:
                self._is_connected = False
            # Don't raise - allow loop to continue
            pass
        except Exception as e:
            # Unexpected error - still continue to avoid thread crash
            with self._connection_lock:
                self._is_connected = False
            pass
    
    def is_connected(self) -> bool:
        """
        Check if client is currently connected.
        
        Returns:
            bool: True if connected, False otherwise
        """
        with self._connection_lock:
            return self._is_connected
    
    def is_running(self) -> bool:
        """
        Check if connection manager is running.
        
        Returns:
            bool: True if manager is active
        """
        return self._running
    
    def get_client(self) -> TCPClient:
        """
        Get the managed TCP client instance.
        
        Returns:
            TCPClient: The managed client
        """
        return self.client
    
    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensures cleanup."""
        self.stop()
    
    def __del__(self):
        """Destructor ensures cleanup."""
        try:
            self.stop()
        except (AttributeError, TypeError):
            # Ignore errors during interpreter shutdown
            pass


# Optional: Factory function for convenience
def create_connection_manager(
    host: str = MAC_HOST, 
    port: int = 8888,
    retry_delay: float = 3.0
) -> ConnectionManager:
    """
    Create a configured connection manager with TCP client.
    
    Args:
        host: Mac AI Brain IP address
        port: TCP port for audio streaming
        retry_delay: Seconds between reconnection attempts
        
    Returns:
        ConnectionManager: Configured connection manager
    """
    client = TCPClient(host, port)
    return ConnectionManager(client, retry_delay)
