"""
Audio Receiver (Mac Side)
------------------------

Receives raw PCM audio bytes from Raspberry Pi via TCPServer
and exposes them as a blocking generator.

IMPORTANT:
- This class NEVER touches raw sockets
- It ONLY uses TCPServer.receive()
- This keeps networking behavior centralized and safe
"""

import time
from typing import Generator

from networking.tcp_server import TCPServer


class AudioReceiver:
    """
    AudioReceiver wraps TCPServer.receive() and yields
    raw PCM audio chunks exactly as sent by Raspberry Pi.
    """

    def __init__(self, tcp_server: TCPServer, recv_size: int = 4096):
        """
        Initialize AudioReceiver.

        Args:
            tcp_server (TCPServer):
                A TCPServer instance with an already accepted client.
            recv_size (int):
                Maximum bytes to read per receive() call.
        """
        self._tcp_server = tcp_server
        self._recv_size = recv_size
        self._running = True

        if not self._tcp_server.is_connected():
            raise RuntimeError("AudioReceiver initialized without an active TCP connection")

    def audio_chunks(self) -> Generator[bytes, None, None]:
        """
        Generator yielding raw PCM audio bytes from Raspberry Pi.

        Yields:
            bytes: LINEAR16 PCM audio data
        """
        try:
            while self._running:
                try:
                    data = self._tcp_server.receive(self._recv_size)
                except ConnectionError:
                    break

                if not data:
                    # No data available, sleep briefly to avoid busy-waiting
                    time.sleep(0.002)  # 2 ms sleep when idle
                    continue

                yield data

        finally:
            self._running = False

    def stop(self):
        """Stop receiving audio."""
        self._running = False
