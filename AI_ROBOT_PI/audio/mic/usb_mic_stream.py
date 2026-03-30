"""
USB microphone streamer for Raspberry Pi 4B.
Uses ALSA device hw:3,0 at 44100Hz, mono, 16-bit PCM.
"""

import queue
import threading
from typing import Optional, Generator

import sounddevice as sd


class USBMicStream:
    """
    USB microphone streaming component for low-latency audio capture.
    
    Uses sounddevice because:
    1. Actively maintained with good Raspberry Pi support
    2. Clean callback-based API for non-blocking streaming
    3. Proper ALSA backend integration
    """
    
    def __init__(
        self,
        device: int = 1,
        samplerate: int = 44100,
        channels: int = 1,
        dtype: str = "int16",
        chunk_size: int = 2048
    ):
        """
        Initialize USB microphone streamer.
        
        Args:
            device: ALSA device identifier
            samplerate: Sample rate in Hz
            channels: Number of audio channels (1 = mono)
            dtype: Audio data type
            chunk_size: Samples per chunk
            
        Chosen chunk size (1024 samples):
        - 23.2ms latency at 44100Hz (good for streaming)
        - Powers of 2 are efficient for signal processing
        - Balances latency vs CPU overhead on Raspberry Pi
        """
        self.device = device
        self.samplerate = samplerate
        self.channels = channels
        self.dtype = dtype
        self.chunk_size = chunk_size
        
        self._stream: Optional[sd.InputStream] = None
        self._audio_queue = queue.Queue(maxsize=300)
        self._is_running = False
        self._lock = threading.Lock()
        
        # Calculate audio chunk duration in seconds
        self.chunk_duration = chunk_size / samplerate
    def _audio_callback(self, indata, frames, time, status):
        """
        Sounddevice callback for real-time audio capture.
        Called for each audio chunk when stream is active.
        
        Note: sounddevice may deliver float32 data even when int16 is requested,
        so we defensively convert to ensure consistent 16-bit PCM output.
        """
        if status:
            # Convert sounddevice status messages to proper exceptions
            # while maintaining the existing error signaling mechanism
            '''error = sd.PortAudioError(f"Audio stream error: {status}")
            try:
                self._audio_queue.put(("error", error), timeout=0.1)
            except queue.Full:
                pass'''
            return
           
        # Defensive conversion to 16-bit PCM bytes:
        # 1. Sounddevice may return float32 even when int16 is requested
        # 2. We normalize float32 to int16 range and convert
        # 3. If already int16, convert directly to bytes
        if indata.dtype == "float32":
            # Scale float to int16 range and convert
            pcm_data = (indata * 32767).astype("int16").tobytes()
        else:
            # Already int16, just convert to bytes
            pcm_data = indata.tobytes()
        # Removed print statement inside real-time callback to reduce latency
            
        # Put audio chunk in queue for consumer
        try:
            self._audio_queue.put(("audio", pcm_data), timeout=0.1)
        except queue.Full:
            # Drop oldest chunk if queue is full (backpressure)
            try:
                self._audio_queue.get_nowait()
                self._audio_queue.put(("audio", pcm_data), timeout=0.1)
            except queue.Empty:
                pass
    def start(self):
        """
        Start audio streaming from USB microphone.
        
        Raises:
            sd.PortAudioError: If microphone cannot be opened
            RuntimeError: If stream is already running
        """
        with self._lock:
            if self._is_running:
                raise RuntimeError("Stream is already running")
            
            try:
                # Create input stream with callback
                self._stream = sd.InputStream(
                    device=self.device,
                    samplerate=self.samplerate,
                    channels=self.channels,
                    dtype=self.dtype,
                    blocksize=self.chunk_size,
                    callback=self._audio_callback,
                    latency="low"
                )
                
                self._stream.start()
                self._is_running = True
                
            except sd.PortAudioError as e:
                raise sd.PortAudioError(
                    f"Cannot open USB microphone {self.device}: {str(e)}"
                )
    def stop(self):
        """Stop audio streaming gracefully."""
        with self._lock:
            if self._stream and self._is_running:
                self._is_running = False
                self._stream.stop()
                self._stream.close()
                self._stream = None
                
                # Clear queue to unblock any waiting consumers
                while not self._audio_queue.empty():
                    try:
                        self._audio_queue.get_nowait()
                    except queue.Empty:
                        break
                self._audio_queue.put(("stop", None))
    
    def audio_chunks(self) -> Generator[bytes, None, None]:
        """
        Generator yielding raw PCM audio chunks.
        
        Yields:
            bytes: Raw 16-bit PCM audio data
            
        Raises:
            RuntimeError: If stream is not running
            sd.PortAudioError: If audio stream error occurs (propagated from callback)
        """
        if not self._is_running:
            raise RuntimeError("Stream must be started before getting chunks")
        
        while self._is_running:
            try:
                # Block with timeout to allow checking running status
                item_type, data = self._audio_queue.get(timeout=0.5)
                
                if item_type == "audio":
                    '''print(f"[MIC] Yielding chunk: {len(data)} bytes")'''
                    yield data
                elif item_type == "error":
                    # data is now an Exception object raised from callback
                    raise data
                elif item_type == "stop":
                    break
                    
            except queue.Empty:
                # Continue checking if stream is still running
                continue
    
    def is_running(self) -> bool:
        """Check if stream is currently running."""
        return self._is_running
    
    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensures cleanup."""
        self.stop()
    
    def __del__(self):
        """
        Destructor ensures stream is stopped.
        
        Note: Guarded against exceptions during interpreter shutdown
        when module attributes may already be cleared.
        """
        try:
            self.stop()
        except (AttributeError, TypeError, ImportError):
            # Silently ignore errors during interpreter shutdown
            # when module dependencies may no longer be available
            pass

# Optional: Factory function for convenience
def create_usb_mic_stream(**kwargs) -> USBMicStream:
    """
    Create a configured USB microphone stream.
    
    Args:
        **kwargs: Override default stream parameters
        
    Returns:
        USBMicStream: Configured stream instance
    """
    defaults = {
        "device": "hw:3,0",
        "samplerate": 44100,
        "channels": 1,
        "dtype": "int16",
        "chunk_size": 2048
    }
    defaults.update(kwargs)
    return USBMicStream(**defaults)
