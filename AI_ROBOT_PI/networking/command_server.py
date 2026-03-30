import socket
import select
import threading
import errno
from typing import Optional, List
from networking.command_protocol import encode_message, decode_messages


class CommandServer:
    """
    TCP server for receiving commands from the Mac client.
    Binds to 0.0.0.0:8890 and accepts one client at a time.
    Uses non-blocking I/O with select for receiving.
    """
    
    # Debug flag - set to True for verbose logging
    DEBUG = False
    
    def __init__(self, host: str = '0.0.0.0', port: int = 8890):
        """
        Initialize the command server.
        
        Args:
            host: Host to bind to (default: 0.0.0.0 for all interfaces)
            port: Port to bind to (default: 8890)
        """
        self.host = host
        self.port = port
        self.server_socket: Optional[socket.socket] = None
        self.client_socket: Optional[socket.socket] = None
        self.client_address: Optional[tuple] = None
        self.running = False
        self.receive_buffer = bytearray()
        self.send_lock = threading.Lock()
        
    def _configure_client_socket(self, sock: socket.socket) -> None:
        """
        Configure client socket for low latency and stability.
        Sets TCP_NODELAY and TCP keepalive options.
        """
        try:
            # Disable Nagle's algorithm for lower latency
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            
            # Enable TCP keepalive
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            
            # Try to set more specific keepalive parameters if available
            try:
                # Linux/Mac specific keepalive parameters
                # Send first keepalive probe after 30 seconds of idle
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 30)
                # Send subsequent probes every 10 seconds
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10)
                # Number of probes before declaring dead
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
            except AttributeError:
                # Platform doesn't support these specific options, that's OK
                pass
                
        except socket.error as e:
            # Non-critical error, just log if debugging
            if self.DEBUG:
                print(f"Warning: Could not set socket options: {e}")
    
    def start(self) -> None:
        """
        Start the command server and bind to the specified host/port.
        """
        try:
            # Create TCP socket
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # Bind to address
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(1)  # Allow only 1 connection in queue
            self.server_socket.setblocking(False)  # Non-blocking
            
            self.running = True
            print(f"Command server started on {self.host}:{self.port}")
            
        except socket.error as e:
            print(f"Failed to start command server: {e}")
            self.close()
            raise
    
    def accept(self) -> bool:
        """
        Accept a new client connection (non-blocking).
        
        Returns:
            bool: True if a client was accepted, False otherwise
        """
        if not self.running or self.client_socket is not None:
            return False
            
        try:
            # Use select to check if there's a connection pending
            readable, _, _ = select.select([self.server_socket], [], [], 0)
            if self.server_socket in readable:
                self.client_socket, self.client_address = self.server_socket.accept()
                self.client_socket.setblocking(False)  # Non-blocking
                
                # Configure socket for low latency and stability
                self._configure_client_socket(self.client_socket)
                
                if self.DEBUG:
                    print(f"Client connected from {self.client_address}")
                return True
                
        except (socket.error, OSError) as e:
            print(f"Error accepting connection: {e}")
            
        return False
    
    def receive_commands(self) -> List[dict]:
        """
        Receive commands from the connected client (non-blocking).
        
        Returns:
            List[dict]: List of decoded command messages
        """
        if not self.running or self.client_socket is None:
            return []
        
        try:
            # Use select to check if there's data to read
            readable, _, exceptional = select.select([self.client_socket], [], [self.client_socket], 0)
            
            if self.client_socket in exceptional:
                print("Client socket in exceptional condition, closing connection")
                self._disconnect_client()
                return []
            
            if self.client_socket in readable:
                # Try to receive data
                try:
                    data = self.client_socket.recv(16384)
                    if data:
                        # Append to receive buffer
                        self.receive_buffer.extend(data)
                        
                        if self.DEBUG and data:
                            print(f"Received {len(data)} bytes from client")
                    else:
                        # Client disconnected
                        if self.DEBUG:
                            print(f"Client {self.client_address} disconnected (graceful)")
                        self._disconnect_client()
                        return []
                        
                except socket.error as e:
                    # No data available (non-blocking socket)
                    if e.errno not in (errno.EAGAIN, errno.EWOULDBLOCK):
                        print(f"Error receiving from client: {e}")
                        self._disconnect_client()
                    return []
        
        except (socket.error, OSError) as e:
            print(f"Select error: {e}")
            self._disconnect_client()
            return []
        
        # Decode complete messages from buffer
        messages = decode_messages(self.receive_buffer)
        
        if self.DEBUG and messages:
            print(f"Decoded {len(messages)} command(s)")
            for i, msg in enumerate(messages):
                print(f"  Command {i+1}: {msg}")
        
        return messages
    
    def send_status(self, obj: dict) -> None:
        """
        Send a status message to the connected client.
        Thread-safe using a lock.
        
        Args:
            obj: Dictionary to send as a status message
        """
        if not self.running or self.client_socket is None:
            return
            
        # Encode the message
        framed_message = encode_message(obj)
        
        if self.DEBUG:
            print(f"Sending status: {obj.get('type', 'unknown')}")
        
        # Use lock for thread-safe sending
        with self.send_lock:
            try:
                self.client_socket.sendall(framed_message)
            except socket.error as e:
                print(f"Failed to send status to client: {e}")
                self._disconnect_client()
    
    def _disconnect_client(self) -> None:
        """
        Disconnect the current client and clean up.
        """
        if self.client_socket:
            try:
                self.client_socket.close()
            except:
                pass
            self.client_socket = None
            self.client_address = None
            self.receive_buffer.clear()
            
            if self.DEBUG:
                print("Client disconnected and cleaned up")
    
    def close(self) -> None:
        """
        Close the server and any client connections.
        """
        self.running = False
        
        # Disconnect client if connected
        self._disconnect_client()
        
        # Close server socket
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
            self.server_socket = None
            
        print("Command server closed")
    
    def is_client_connected(self) -> bool:
        """
        Check if a client is currently connected.
        
        Returns:
            bool: True if client is connected, False otherwise
        """
        return self.client_socket is not None and self.running
    
    def __del__(self):
        """Ensure cleanup on deletion."""
        if self.running:
            self.close()


# Example usage and test
if __name__ == "__main__":
    import time
    
    def server_test():
        """Simple test of the command server."""
        server = CommandServer()
        server.DEBUG = True  # Enable debug for test
        
        try:
            server.start()
            
            print("Waiting for client connection...")
            
            # Main server loop
            while True:
                # Try to accept new client
                if not server.is_client_connected():
                    server.accept()
                
                # Receive commands from connected client
                commands = server.receive_commands()
                
                # Process received commands
                for cmd in commands:
                    print(f"Received command: {cmd}")
                    
                    # Example: Send echo response
                    if cmd.get("type") == "test":
                        response = {
                            "type": "status",
                            "message": f"Echo: {cmd.get('data', '')}",
                            "timestamp": time.time()
                        }
                        server.send_status(response)
                
                # Simulate other work
                time.sleep(0.1)
                
        except KeyboardInterrupt:
            print("\nShutting down server...")
        finally:
            server.close()
    
    server_test()
