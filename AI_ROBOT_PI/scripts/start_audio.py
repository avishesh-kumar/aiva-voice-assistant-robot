"""
Phase-1 startup script for Raspberry Pi 4B audio streaming.
Wires together microphone capture, TCP networking, and speaker playback.
This is the main entry point for Phase 1 audio functionality.
"""

import sys
import time
import signal
from pathlib import Path
import numpy as np

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.network_config import MAC_HOST

# TTS volume scaling (0.0 to 1.0, where 1.0 = full volume)
TTS_GAIN = 0.5  # Set to 1.0 to disable volume scaling

# Speaker expects frames of 1024 samples at 16-bit (2048 bytes)
TTS_FRAME_BYTES = 2048  # 1024 samples * 2 bytes per sample

# STOP_SPEAKING control marker
STOP_SPEAKING_MARKER = b"__STOP_SPEAKING__"

# Reconnection settings
RECONNECT_RETRY_DELAY = 2.0  # seconds between reconnection attempts
TTS_TIMEOUT_SECONDS = 2.0    # Time to wait for TTS data before considering connection dead

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import Phase-1 components
try:
    from audio.mic.usb_mic_stream import create_usb_mic_stream
    from networking.connection_manager import create_connection_manager
    from audio.speaker.speaker_player import create_speaker_player
    from networking.tts_tcp_client import TTSTCPClient
except ImportError as e:
    print(f"ERROR: Failed to import required modules: {e}")
    print("Make sure all Phase-1 components are implemented.")
    sys.exit(1)


def load_config():
    """
    Load configuration from YAML files.
    Returns dicts with audio and network settings.
    """
    config_dir = project_root / "config"
    
    # Default configuration (used if YAML files don't exist or fail to load)
    default_config = {
        "audio": {
            "mic_device": "hw:3,0",
            "speaker_device": "hw:0,0",
            "samplerate": 44100,
            "channels": 1,
            "chunk_size": 1024
        },
        "network": {
            "host": MAC_HOST,
            "port": 8888,
            "retry_delay": 3.0
        }
    }
    
    # Try to load from YAML files
    try:
        import yaml
        
        audio_config_path = config_dir / "audio_config.yaml"
        if audio_config_path.exists():
            with open(audio_config_path, 'r') as f:
                audio_config = yaml.safe_load(f)
                if audio_config:
                    default_config["audio"].update(audio_config)
                    print("Loaded audio configuration")
        
        network_config_path = config_dir / "network_config.yaml"
        if network_config_path.exists():
            with open(network_config_path, 'r') as f:
                network_config = yaml.safe_load(f)
                if network_config:
                    network_config.pop("host", None) 
                    default_config["network"].update(network_config)
                    print("Loaded network configuration")
                    
    except ImportError:
        print("Note: PyYAML not installed, using default configuration")
    except Exception as e:
        print(f"Warning: Failed to load config files: {e}")
    
    return default_config["audio"], default_config["network"]


class AudioStreamingSystem:
    """
    Main system that wires together all Phase-1 components.
    Manages the complete audio streaming lifecycle.
    """
    
    def __init__(self):
        """Initialize the audio streaming system."""
        self.mic_stream = None
        self.tcp_client = None
        self.connection_manager = None
        self.speaker_player = None
        self.tts_client = None
        self.running = False
        self._tts_buffer = b""  # Buffer for TTS audio bytes
        self.robot_speaking = False
        self._last_tts_time = 0.0
        self._last_tts_packet_time = 0.0  # Track last time we received any TTS data
        self._stop_marker_buffer = b""  # Buffer for handling split markers
        
        # TTS reconnection state
        self._tts_reconnecting = False
        self._tts_reconnect_attempts = 0

        # Load configuration
        self.audio_config, self.network_config = load_config()
        
    def _handle_stop_speaking(self):
        """
        Immediately stop ongoing speech playback.
        Clears buffers and resets state without closing the speaker stream.
        """
        print("[STOP_SPEAKING] Received - stopping speech immediately")
        
        # Clear the TTS buffer
        self._tts_buffer = b""
        
        # Stop speaker player immediately (flushes buffer but keeps stream open)
        if self.speaker_player:
            self.speaker_player.stop_immediately()
        
        # Reset speaking state
        self.robot_speaking = False
        self._last_tts_time = 0.0
        self._last_tts_packet_time = 0.0
        
        print("[STOP_SPEAKING] Speech stopped, ready for new audio")
    
    def _check_for_stop_marker(self, data: bytes) -> tuple[bool, bytes]:
        """
        Detect STOP_SPEAKING marker in stream while handling packet splits.

        Returns:
            (found_marker, audio_bytes_without_marker)
        """
        if not data:
            return False, b""

        buf = self._stop_marker_buffer + data

        if STOP_SPEAKING_MARKER in buf:
            cleaned = buf.replace(STOP_SPEAKING_MARKER, b"")
            self._stop_marker_buffer = b""
            return True, cleaned

        # Keep only tail bytes to detect a split marker next time
        keep = len(STOP_SPEAKING_MARKER) - 1
        if keep < 1:
            keep = 1

        if len(buf) > keep:
            self._stop_marker_buffer = buf[-keep:]
            return False, buf[:-keep]

        # Not enough bytes yet to decide, hold them
        self._stop_marker_buffer = buf
        return False, b""

    
    def _process_tts_buffer(self):
        """
        Process buffered TTS audio into fixed-size frames and send to speaker.
        Only sends complete frames of TTS_FRAME_BYTES size.
        """
        # Process complete frames from buffer
        while len(self._tts_buffer) >= TTS_FRAME_BYTES:
            # Extract a complete frame
            frame_bytes = self._tts_buffer[:TTS_FRAME_BYTES]
            self._tts_buffer = self._tts_buffer[TTS_FRAME_BYTES:]
            
            # Apply volume scaling if needed
            if TTS_GAIN != 1.0:
                pcm = np.frombuffer(frame_bytes, dtype=np.int16).astype(np.float32)
                pcm = np.clip(pcm * TTS_GAIN, -32768, 32767).astype(np.int16)
                frame_bytes = pcm.tobytes()
            
            # Send the properly sized frame to the speaker
            self.speaker_player.add_audio(frame_bytes)
    
    def _connect_tts_client(self) -> bool:
        """
        Connect or reconnect TTS client.
        
        Returns:
            bool: True if connected successfully, False otherwise
        """
        if self._tts_reconnecting:
            return False
            
        self._tts_reconnecting = True
        try:
            # Clean up old connection if exists
            if self.tts_client:
                try:
                    self.tts_client.close()
                except:
                    pass
            
            print(f"[AUDIO][TTS] Connecting TTS client to {self.network_config.get('host', MAC_HOST)}:8889")
            self.tts_client = TTSTCPClient(
                host=self.network_config.get("host", MAC_HOST),
                port=8889
            )
            self.tts_client.connect()
            self._tts_reconnect_attempts = 0
            self._tts_reconnecting = False
            print("[AUDIO][TTS] TTS connection established")
            return True
            
        except Exception as e:
            self._tts_reconnect_attempts += 1
            print(f"[AUDIO][TTS] Failed to connect TTS client (attempt {self._tts_reconnect_attempts}): {e}")
            self.tts_client = None
            self._tts_reconnecting = False
            return False
    
    def start(self):
        """Start all components and begin audio streaming."""
        print("=" * 50)
        print("Starting Phase-1 Audio Streaming System")
        print("=" * 50)
        try:
            # Step 1: Create and start speaker player
            print("[AUDIO] Initializing speaker player...")
            self.speaker_player = create_speaker_player(
                device=self.audio_config.get("speaker_device", "hw:0,0"),
                samplerate=self.audio_config.get("samplerate", 44100),
                channels=self.audio_config.get("channels", 1)
            )
            self.speaker_player.start()
            print("[AUDIO] Speaker player started")
            
            # Step 2: Connect TTS client
            print("[AUDIO][TTS] Initializing TTS connection...")
            if not self._connect_tts_client():
                print("[AUDIO][TTS] Warning: TTS connection failed initially, will retry in main loop")
            
            # Step 3: Create connection manager (which creates TCP client internally)
            print("[AUDIO] Initializing network connection...")
            self.connection_manager = create_connection_manager(
                host=self.network_config.get("host", MAC_HOST),
                port=self.network_config.get("port", 8888),
                retry_delay=self.network_config.get("retry_delay", 3.0)
            )
            self.connection_manager.start()
            print("[AUDIO] Connection manager started")
            
            # Get TCP client from connection manager
            self.tcp_client = self.connection_manager.get_client()
            
            # Step 4: Create and start microphone stream
            print("[AUDIO] Initializing microphone stream...")
            self.mic_stream = create_usb_mic_stream(
                device=self.audio_config.get("mic_device", "hw:3,0"),
                samplerate=self.audio_config.get("samplerate", 44100),
                channels=self.audio_config.get("channels", 1),
                chunk_size=self.audio_config.get("chunk_size", 2048)
            )
            self.mic_stream.start()
            print("[AUDIO] Microphone stream started")
            
            self.running = True
            print("\n" + "=" * 50)
            print("[AUDIO] System READY - Streaming audio...")
            print(f"[AUDIO] Target: {self.network_config.get('host')}:{self.network_config.get('port')}")
            print("[AUDIO] Press Ctrl+C to stop")
            print("=" * 50 + "\n")
            
        except Exception as e:
            print(f"[AUDIO] ERROR: Failed to start system: {e}")
            self.stop()
            raise
    
    def stop(self):
        """Stop all components gracefully."""
        print("\n[AUDIO] Shutting down system...")
        self.running = False
        
        # Stop components in reverse order
        if self.mic_stream:
            print("[AUDIO] Stopping microphone stream...")
            self.mic_stream.stop()
            print("[AUDIO] Microphone stopped")
        
        if self.connection_manager:
            print("[AUDIO] Stopping connection manager...")
            self.connection_manager.stop()
            print("[AUDIO] Connection manager stopped")
        
        if self.speaker_player:
            print("[AUDIO] Stopping speaker player...")
            self.speaker_player.stop()
            print("[AUDIO] Speaker player stopped")
        
        if self.tts_client:
            try:
                self.tts_client.close()
            except:
                pass

        print("[AUDIO] System shutdown complete.")
    
    def _handle_tts_timeout(self, current_time: float):
        """
        Handle TTS timeout - if no data received for too long while robot is speaking,
        consider TTS ended and reset state.
        """
        if self.robot_speaking:
            time_since_last_packet = current_time - self._last_tts_packet_time
            if time_since_last_packet > TTS_TIMEOUT_SECONDS:
                print(f"[AUDIO][TTS] TTS timeout ({time_since_last_packet:.1f}s), resetting speaking state")
                self.robot_speaking = False
                self._tts_buffer = b""
                self._last_tts_time = 0.0
                self._last_tts_packet_time = 0.0
    
    def run(self):
        """
        Main audio streaming loop.
        Sends microphone audio to server and plays received audio.
        """
        if not self.running:
            print("[AUDIO] ERROR: System not started. Call start() first.")
            return
        
        last_tts_reconnect_attempt = 0.0
        consecutive_none_receives = 0
        
        try:
            # Main audio streaming loop
            for mic_chunk in self.mic_stream.audio_chunks():
                if not self.running:
                    break
                
                # Send microphone audio if connected
                if self.connection_manager.is_connected():
                    if not self.robot_speaking:
                        self.tcp_client.send(mic_chunk)
                    else:
                        # Generate dynamic silence frame matching mic_chunk size
                        silence_chunk = b"\x00" * len(mic_chunk)
                        self.tcp_client.send(silence_chunk)
                
                # Check TTS connection and reconnect if needed
                current_time = time.monotonic()
                
                # Check for TTS timeout
                self._handle_tts_timeout(current_time)
                
                if self.tts_client is None:
                    if current_time - last_tts_reconnect_attempt >= RECONNECT_RETRY_DELAY:
                        print("[AUDIO][TTS] Attempting to reconnect TTS client...")
                        if self._connect_tts_client():
                            print("[AUDIO][TTS] TTS client reconnected successfully")
                        last_tts_reconnect_attempt = current_time
                else:
                    # Receive TTS audio from Mac (speaker-only socket)
                    try:
                        tts_audio = self.tts_client.receive()
                        
                        if tts_audio is not None:
                            # Reset consecutive none counter
                            consecutive_none_receives = 0
                            
                            # Update packet time
                            self._last_tts_packet_time = current_time
                            
                            # Check for STOP_SPEAKING control marker (handles packet splits)
                            has_stop_marker, processed_data = self._check_for_stop_marker(tts_audio)
                            
                            if has_stop_marker:
                                self._handle_stop_speaking()
                                # If there's remaining data after the marker, process it as audio
                                if processed_data:
                                    self._tts_buffer += processed_data
                                    self._process_tts_buffer()
                                continue  # Skip further processing for this chunk
                            else:
                                # No marker found, process as audio
                                if processed_data:
                                    # Add processed bytes to buffer
                                    self._tts_buffer += processed_data
                                    
                                    # Mark that robot is speaking
                                    self.robot_speaking = True
                                    self._last_tts_time = current_time
                                    
                                    # Process complete frames from buffer
                                    self._process_tts_buffer()
                        else:
                            # No data available this iteration
                            consecutive_none_receives += 1
                            # If we get many consecutive None receives, check connection health
                            if consecutive_none_receives > 100 and self.robot_speaking:
                                time_since_last_packet = current_time - self._last_tts_packet_time
                                if time_since_last_packet > 1.0:  # 1 second without data
                                    print(f"[AUDIO][TTS] No TTS data for {time_since_last_packet:.1f}s, checking connection")
                    
                    except ConnectionError as e:
                        # TTS connection error - log and attempt reconnection
                        print(f"[AUDIO][TTS] Connection error: {e}")
                        if self.tts_client:
                            try:
                                self.tts_client.close()
                            except:
                                pass
                        self.tts_client = None
                        self.robot_speaking = False
                        self._tts_buffer = b""
                        last_tts_reconnect_attempt = current_time
                        consecutive_none_receives = 0
                    except Exception as e:
                        # Other TTS connection errors - log and attempt reconnection
                        print(f"[AUDIO][TTS] Unexpected error: {e}")
                        if self.tts_client:
                            try:
                                self.tts_client.close()
                            except:
                                pass
                        self.tts_client = None
                        self.robot_speaking = False
                        self._tts_buffer = b""
                        last_tts_reconnect_attempt = current_time
                        consecutive_none_receives = 0
                
                # Re-enable mic only after TTS has fully finished
                if self.robot_speaking:
                    silence_time = time.monotonic() - self._last_tts_time
                    
                    # Reduced latency: resume mic after 120ms of silence AND minimal buffer
                    if silence_time > 0.12 and self.speaker_player.get_queue_size() <= 1:
                        # Also check if we have any pending buffered data
                        if len(self._tts_buffer) < TTS_FRAME_BYTES:
                            self.robot_speaking = False
                            self._tts_buffer = b""
                            # Optional: log when mic is resumed
                            # print("[AUDIO] Mic resumed after TTS")
                
                # Small sleep to prevent CPU spinning
                time.sleep(0.0005)
                
        except KeyboardInterrupt:
            print("\n[AUDIO] Interrupt received...")
        except Exception as e:
            print(f"[AUDIO] ERROR in main loop: {e}")
        finally:
            self.stop()


def signal_handler(signum, frame):
    """Handle termination signals."""
    print(f"\n[AUDIO] Signal {signum} received. Shutting down...")
    sys.exit(0)


def main():
    """Main entry point for Phase-1 audio streaming."""
    # Register signal handlers for clean shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create and run the system
    system = AudioStreamingSystem()
    
    try:
        system.start()
        system.run()
    except Exception as e:
        print(f"[AUDIO] FATAL ERROR: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
