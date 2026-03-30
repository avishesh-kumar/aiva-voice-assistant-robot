import socket
import select
import time
import errno

class TTSTCPClient:
    def __init__(self, host: str, port: int = 8889):
        self.host = host
        self.port = port
        self.sock = None

    def connect(self, retries=10, delay=1.0):
        """Connect to TTS server with retry logic and optimal socket options."""
        for attempt in range(retries):
            try:
                # Create TCP socket
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                
                # Set TCP_NODELAY to disable Nagle's algorithm for low latency
                self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                
                # Enable TCP keep-alive
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                
                # Set keep-alive parameters if available (Linux-specific)
                try:
                    # TCP_KEEPIDLE: time to start sending keep-alive probes
                    self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 30)
                    # TCP_KEEPINTVL: interval between keep-alive probes
                    self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10)
                    # TCP_KEEPCNT: number of keep-alive probes before dropping connection
                    self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
                except (AttributeError, OSError):
                    # These options might not be available on all platforms
                    pass
                
                # Connect to server
                self.sock.connect((self.host, self.port))
                
                # Set non-blocking mode for responsive I/O
                self.sock.setblocking(False)
                
                print(f"[TTS] Connected to {self.host}:{self.port} (attempt {attempt + 1}/{retries})")
                return
                
            except (ConnectionRefusedError, socket.timeout, OSError) as e:
                # Clean up failed socket
                if self.sock:
                    try:
                        self.sock.close()
                    except:
                        pass
                    self.sock = None
                
                if attempt < retries - 1:
                    print(f"[TTS] Connection attempt {attempt + 1}/{retries} failed: {e}. Retrying in {delay}s...")
                    time.sleep(delay)
                else:
                    raise ConnectionError(f"TTS server {self.host}:{self.port} not available after {retries} attempts")
        
        raise ConnectionError("TTS server not available")

    def receive(self, size: int = 4096):
        """
        Receive data from TTS socket non-blockingly.
        Returns None if no data available, raises ConnectionError if disconnected.
        """
        if not self.sock:
            return None

        try:
            # Use select with zero timeout for non-blocking check
            ready, _, _ = select.select([self.sock], [], [], 0)
            if not ready:
                return None  # No data available

            data = self.sock.recv(size)
            if not data:
                # Empty response means remote closed connection
                raise ConnectionError("TTS server closed connection")
            
            return data

        except ConnectionError:
            # Re-raise connection errors
            raise
        except socket.timeout:
            # Shouldn't happen with non-blocking socket, but handle gracefully
            return None
        except OSError as e:
            if e.errno == errno.EAGAIN or e.errno == errno.EWOULDBLOCK:
                # No data available in non-blocking mode
                return None
            elif e.errno == errno.ECONNRESET or e.errno == errno.ECONNABORTED:
                raise ConnectionError(f"TTS connection lost: {e}")
            else:
                # Unexpected socket error
                raise ConnectionError(f"TTS socket error: {e}")
        except Exception as e:
            # Catch-all for any other exceptions
            raise ConnectionError(f"Unexpected TTS receive error: {e}")

    def close(self):
        """Safely close the TTS socket connection."""
        if self.sock:
            try:
                # Shutdown socket before close for clean termination
                self.sock.shutdown(socket.SHUT_RDWR)
            except:
                pass  # Socket might already be partially closed
            
            try:
                self.sock.close()
            except:
                pass  # Ignore errors during close
            
            self.sock = None
            print("[TTS] Connection closed")
