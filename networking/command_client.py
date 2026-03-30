import socket
import select
from typing import List
from networking.command_protocol import encode_message, decode_messages


class CommandClient:
    """
    TCP client for forwarding AI intents to an external executor (e.g. motor/vision system).

    IMPORTANT:
    - This client DOES NOT execute anything
    - It ONLY forwards structured intent dictionaries
    - It MAY receive status/ack messages, but does not depend on them
    """

    def __init__(self, host: str, port: int = 8890):
        self.host = host
        self.port = port
        self.socket = None
        self.recv_buffer = bytearray()
        self._connected = False

    # ------------------------------------------------------------
    # Connection handling
    # ------------------------------------------------------------

    def connect(self) -> bool:
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(3.0)
            self.socket.connect((self.host, self.port))
            self.socket.setblocking(False)
            self._connected = True
            print(f"[IntentClient] Connected to {self.host}:{self.port}")
            return True
        except Exception as e:
            self.close()
            raise ConnectionError(f"Failed to connect: {e}")

    def close(self) -> None:
        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
        self.socket = None
        self._connected = False
        self.recv_buffer.clear()
        print("[IntentClient] Connection closed")

    def is_connected(self) -> bool:
        if not self._connected or not self.socket:
            return False
        try:
            _, _, errors = select.select([self.socket], [], [self.socket], 0)
            return not bool(errors)
        except Exception:
            return False

    # ------------------------------------------------------------
    # Intent forwarding (NO execution semantics)
    # ------------------------------------------------------------

    def send_intent(self, intent: dict) -> bool:
        """
        Forward a structured intent dictionary to executor system.

        The assistant does NOT care what happens after this.
        """
        if not self.is_connected():
            print("[IntentClient] Not connected, intent not sent")
            return False

        try:
            framed = encode_message(intent)
            total_sent = 0

            while total_sent < len(framed):
                try:
                    sent = self.socket.send(framed[total_sent:])
                    if sent == 0:
                        raise ConnectionError("Socket closed")
                    total_sent += sent
                except BlockingIOError:
                    select.select([], [self.socket], [], 0.1)

            return True

        except Exception as e:
            print(f"[IntentClient] Failed to send intent: {e}")
            self.close()
            return False

    # ------------------------------------------------------------
    # Optional status reception (PASSIVE)
    # ------------------------------------------------------------

    def poll_messages(self) -> List[dict]:
        """
        Non-blocking receive of messages from executor.
        Assistant does NOT rely on these.
        """
        if not self.is_connected():
            return []

        try:
            ready, _, errors = select.select([self.socket], [], [self.socket], 0)
            if errors or not ready:
                return []

            chunk = self.socket.recv(4096)
            if not chunk:
                self.close()
                return []

            self.recv_buffer.extend(chunk)
            return decode_messages(self.recv_buffer)

        except Exception:
            return []
