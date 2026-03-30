import time
import threading
from networking.tcp_server import TCPServer


class AudioSender:
    SAMPLE_RATE = 44100
    FRAME_SAMPLES = 1024
    BYTES_PER_SAMPLE = 2
    FRAME_BYTES = FRAME_SAMPLES * BYTES_PER_SAMPLE
    FRAME_DURATION = FRAME_SAMPLES / SAMPLE_RATE  # ~23.2 ms

    def __init__(self, tcp_server: TCPServer):
        self._tcp_server = tcp_server
        self._conn = tcp_server._client_socket
        if self._conn is None:
            raise RuntimeError("AudioSender initialized without an active TCP connection")

        self._stop_event = threading.Event()

    def reset(self):
        """Allow streaming again after a stop()."""
        self._stop_event.clear()

    def stream_paced(self, pcm_audio: bytes):
        if not pcm_audio:
            return

        # Allow new playback
        self.reset()
        self._conn.setblocking(False)

        try:
            next_frame_time = time.monotonic()

            for i in range(0, len(pcm_audio), self.FRAME_BYTES):
                if self._stop_event.is_set():
                    break

                frame = pcm_audio[i:i + self.FRAME_BYTES]
                if len(frame) < self.FRAME_BYTES:
                    break

                # Send frame
                try:
                    self._conn.send(frame)
                except BlockingIOError:
                    pass


                next_frame_time += self.FRAME_DURATION
                sleep_time = next_frame_time - time.monotonic()

                if sleep_time > 0:
                    # Sleep in tiny steps so stop is faster
                    end_time = time.monotonic() + sleep_time
                    while time.monotonic() < end_time:
                        if self._stop_event.is_set():
                            break
                        time.sleep(0.003)

        except OSError:
            # Connection lost
            self._stop_event.set()

    def stop(self):
        """Interrupt current streaming immediately."""
        self._stop_event.set()
