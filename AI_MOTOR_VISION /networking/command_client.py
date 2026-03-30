import socket
import select
import time
from typing import List, Optional
from networking.command_protocol import encode_message, decode_messages
from utils.logger import setup_logger
logger = setup_logger("NETWORK", log_file="network.log")


class CommandClient:
    """
    TCP client for connecting to Pi command server with framed JSON protocol.
    """
    
    def __init__(self, host: str, port: int = 8890):
        """
        Initialize the command client.
        
        Args:
            host: Pi server hostname or IP address
            port: Pi server port (default: 8890)
        """
        self.host = host
        self.port = port
        self.socket = None
        self.recv_buffer = bytearray()
        self._connected = False
        
    def connect(self) -> bool:
        """
        Connect to the Pi command server.
        
        Returns:
            bool: True if connection successful
            
        Raises:
            ConnectionError: If connection fails (timeout or refused)
        """
        try:
            # Create TCP socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            
            # Set timeout for connection attempt
            self.socket.settimeout(3.0)
            
            # Attempt to connect
            self.socket.connect((self.host, self.port))
            
            # Connection successful, set to non-blocking for subsequent operations
            self.socket.setblocking(False)
            self._connected = True
            
            logger.info(f"Connected to Pi command server at {self.host}:{self.port}")
            return True
            
        except socket.timeout:
            self._close_socket()
            raise ConnectionError(f"Connection timeout to {self.host}:{self.port}")
        except ConnectionRefusedError:
            self._close_socket()
            raise ConnectionError(f"Connection refused by {self.host}:{self.port}")
        except Exception as e:
            self._close_socket()
            raise ConnectionError(f"Failed to connect to {self.host}:{self.port}: {e}")
    
    def _close_socket(self):
        """Close socket and reset connection state."""
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
        self.socket = None
        self._connected = False
        self.recv_buffer.clear()
    
    def close(self) -> None:
        """
        Close the connection to the Pi command server.
        """
        self._close_socket()
        logger.info("Command server connection closed")
    
    def is_connected(self) -> bool:
        """
        Check if connected to the Pi command server.
        
        Returns:
            bool: True if connected, False otherwise
        """
        if not self._connected or not self.socket:
            return False
            
        # Verify the socket is still alive
        try:
            # Try a non-blocking recv with 0 timeout
            ready_to_read, _, errors = select.select([self.socket], [], [self.socket], 0)
            if errors:
                return False
            return True
        except (ValueError, OSError):
            return False
    
    def send_command(self, command: dict) -> bool:
        """
        Send a command to the Pi command server.
        
        Args:
            command: Dictionary containing command data
            
        Returns:
            bool: True if command sent successfully, False otherwise
        """
        if not self.is_connected():
            logger.warning("Not connected to command server, cannot send command")
            return False
        
        try:
            # Encode the command using framed JSON protocol
            framed_data = encode_message(command)
            
            # Send all data
            total_sent = 0
            while total_sent < len(framed_data):
                try:
                    sent = self.socket.send(framed_data[total_sent:])
                    if sent == 0:
                        raise ConnectionError("Socket connection broken")
                    total_sent += sent
                except BlockingIOError:
                    # Wait a bit and try again
                    ready_to_write, _, errors = select.select(
                        [], [self.socket], [self.socket], 0.1
                    )
                    if errors:
                        raise ConnectionError("Socket error")
            
            return True
            
        except Exception as e:
            logger.exception("Failed to send command")
            self.close()
            return False
    
    def poll_status(self) -> List[dict]:
        """
        Non-blocking read from command socket.
        Returns list of decoded status dicts.
        
        Returns:
            List[dict]: List of decoded status messages, empty list if none available
        """
        if not self.is_connected():
            return []
        
        try:
            # Check if there's data available to read
            ready_to_read, _, errors = select.select([self.socket], [], [self.socket], 0)
            
            if errors:
                logger.warning("Socket error detected while polling status")
                self.close()
                return []
            
            if not ready_to_read:
                # No data available
                return []
            
            # Read available data
            chunk = self.socket.recv(4096)
            if not chunk:
                # Connection closed by server
                logger.warning("Command server closed connection")
                self.close()
                return []
            
            # Append bytes to buffer
            self.recv_buffer.extend(chunk)
            
            # Decode messages using decode_messages
            messages = decode_messages(self.recv_buffer)
            
            # Return list of decoded messages
            return messages
            
        except BlockingIOError:
            # No data available (shouldn't happen due to select check)
            return []
        except ConnectionError as e:
            logger.exception("Connection error while polling status")
            self.close()
            return []
        except Exception as e:
            logger.exception("Unexpected error while receiving messages")
            # Don't close on other errors, just return empty
            return []
    
    def receive_messages(self) -> List[dict]:
        """
        Alias for poll_status for backward compatibility.
        
        Returns:
            List[dict]: List of decoded messages
        """
        return self.poll_status()


# Example usage and testing
if __name__ == "__main__":
    # Example commands
    motor_commands = [
        {"type": "motor", "action": "forward", "speed": 0.5, "duration": 2.0},
        {"type": "motor", "action": "stop"},
        {"type": "camera", "action": "capture"},
        {"type": "status", "action": "get_battery"},
    ]
    
    # Test the client
    client = CommandClient("localhost", 8890)  # Change to actual Pi IP
    
    try:
        if client.connect():
            print("Connected successfully!")
            
            # Send some test commands
            for cmd in motor_commands:
                print(f"Sending command: {cmd}")
                if client.send_command(cmd):
                    print("  Command sent successfully")
                    
                    # Wait a bit and check for responses
                    time.sleep(0.1)
                    responses = client.poll_status()
                    if responses:
                        print(f"  Received responses: {responses}")
                    else:
                        print("  No responses")
                else:
                    print("  Failed to send command")
                    break
            
            # Try receiving any remaining messages
            print("\nReceiving any remaining messages...")
            responses = client.poll_status()
            if responses:
                print(f"Received: {responses}")
            
            # Clean up
            client.close()
    except ConnectionError as e:
        print(f"Failed to connect: {e}")
