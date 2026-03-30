"""
Speaker playback component for Raspberry Pi 4B.
Plays raw PCM audio bytes received from Mac AI Brain.
Uses default ALSA device (hw:0,0) at 44100Hz, mono, 16-bit PCM.
"""

import queue
import threading
from typing import Optional

import sounddevice as sd
import numpy as np


class SpeakerPlayer:
    """
    Speaker player for low-latency PCM audio playback.
    
    Acts as a dumb sink for audio bytes received over network.
    Uses sounddevice for consistent audio handling with microphone.
    """
    
    def __init__(
        self,
        device: str = "hw:0,0",
        samplerate: int = 44100,
        channels: int = 1,
        dtype: str = "int16",
        buffer_size: int = 5
    ):
        """
        Initialize speaker player.
        
        Args:
            device: ALSA output device identifier
            samplerate: Sample rate in Hz (must match source)
            channels: Number of audio channels (1 = mono)
            dtype: Audio data type (must be int16 for PCM)
            buffer_size: Number of audio chunks to buffer for jitter smoothing
            
        Buffer size of 5 chunks (~116ms at 1024 samples):
        - Smooths network jitter without excessive latency
        - Prevents underruns while maintaining low latency
        - Drops old audio when overloaded (backpressure)
        """
        self.device = device
        self.samplerate = samplerate
        self.channels = channels
        self.dtype = dtype
        
        self._stream: Optional[sd.OutputStream] = None
        self._audio_queue = queue.Queue(maxsize=buffer_size)
        self._is_running = False
        self._lock = threading.Lock()
        
    def _audio_callback(self, outdata, frames, time, status):
        """
        Sounddevice callback for real-time audio playback.
        Called when output stream needs more audio data.
        
        Returns silence if no audio available (prevents underrun).
        """
        if status:
            # Handle stream status, but don't raise in callback thread
            outdata.fill(0)
            return
            
        try:
            # Get next audio chunk from queue (non-blocking)
            audio_bytes = self._audio_queue.get_nowait()
            
            # Convert bytes to numpy array for sounddevice
            audio_array = np.frombuffer(audio_bytes, dtype=np.int16)
            
            # Always fill with zeros first
            outdata.fill(0)
            
            # Copy only available samples to avoid shape mismatch
            num_samples = min(len(audio_array), frames)
            
            if num_samples > 0:
                # Convert to float32 for sounddevice
                audio_float = audio_array[:num_samples].astype(np.float32) / 32768.0
                
                if self.channels == 1:
                    outdata[:num_samples, 0] = audio_float
                else:
                    # Handle stereo by duplicating mono channel
                    outdata[:num_samples, :] = np.column_stack([audio_float, audio_float])
                
        except queue.Empty:
            # No audio available - output silence
            outdata.fill(0)
        except Exception:
            # Any other error - output silence to keep stream alive
            outdata.fill(0)
    
    def add_audio(self, audio_bytes: bytes) -> None:
        """
        Add PCM audio bytes to playback queue.
        
        Drops oldest chunk if queue is full (backpressure handling).
        
        Args:
            audio_bytes: Raw 16-bit PCM audio data
            
        Raises:
            RuntimeError: If player is not running
        """
        if not self._is_running:
            raise RuntimeError("Speaker player must be started before adding audio")
        
        try:
            # Put audio in queue, drop oldest if full
            self._audio_queue.put_nowait(audio_bytes)
        except queue.Full:
            # Drop oldest chunk to make room
            try:
                self._audio_queue.get_nowait()
                self._audio_queue.put_nowait(audio_bytes)
            except queue.Empty:
                pass
    
    def start(self) -> None:
        """
        Start audio playback stream.
        
        Raises:
            sd.PortAudioError: If speaker device cannot be opened
            RuntimeError: If stream is already running
        """
        with self._lock:
            if self._is_running:
                raise RuntimeError("Speaker player is already running")
            
            try:
                # Create output stream with callback
                self._stream = sd.OutputStream(
                    device=self.device,
                    samplerate=self.samplerate,
                    channels=self.channels,
                    dtype="float32",  # Sounddevice callback uses float32
                    callback=self._audio_callback,
                    blocksize=1024,  # Match common audio chunk size
                    latency="low"
                )
                
                self._stream.start()
                self._is_running = True
                
            except sd.PortAudioError as e:
                raise sd.PortAudioError(
                    f"Cannot open speaker device {self.device}: {str(e)}"
                )
    
    def stop(self) -> None:
        """Stop audio playback and close stream."""
        with self._lock:
            if self._stream and self._is_running:
                self._is_running = False
                self._stream.stop()
                self._stream.close()
                self._stream = None
                
                # Clear queue to free memory
                while not self._audio_queue.empty():
                    try:
                        self._audio_queue.get_nowait()
                    except queue.Empty:
                        break
    
    def flush(self) -> None:
        """
        Immediately clear any queued audio chunks so speech stops quickly.
        
        Thread-safe and safe to call while playing. Does not close the stream.
        """
        with self._lock:
            # Clear the audio queue
            while not self._audio_queue.empty():
                try:
                    self._audio_queue.get_nowait()
                except queue.Empty:
                    break
    
    def stop_immediately(self) -> None:
        """
        Stop ongoing speech immediately without closing the stream.
        
        This clears all buffered audio and resets the audio stream to a clean state,
        allowing new audio to be played immediately without interruption.
        """
        # Clear all buffered audio
        self.flush()
        
        # Note: We cannot stop/restart the stream here as that would close it
        # The stream remains open and ready for new audio
        # The callback will output silence until new audio is added
    
    def clear_buffer(self) -> None:
        """Clear any buffered audio without stopping playback."""
        # Use flush() which is thread-safe and does the same thing
        self.flush()
    
    def is_running(self) -> bool:
        """Check if speaker player is currently running."""
        return self._is_running
    
    def get_queue_size(self) -> int:
        """Get current number of audio chunks in buffer."""
        return self._audio_queue.qsize()
    
    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensures cleanup."""
        self.stop()
    
    def __del__(self):
        """Destructor ensures playback is stopped."""
        try:
            self.stop()
        except (AttributeError, TypeError, ImportError):
            # Ignore errors during interpreter shutdown
            pass

# Optional: Factory function for convenience
def create_speaker_player(**kwargs) -> SpeakerPlayer:
    """
    Create a configured speaker player.
    
    Args:
        **kwargs: Override default player parameters
        
    Returns:
        SpeakerPlayer: Configured player instance
    """
    defaults = {
        "device": "hw:0,0",
        "samplerate": 44100,
        "channels": 1,
        "dtype": "int16",
        "buffer_size": 5
    }
    defaults.update(kwargs)
    return SpeakerPlayer(**defaults)
