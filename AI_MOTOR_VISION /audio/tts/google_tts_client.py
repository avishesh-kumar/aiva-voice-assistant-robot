"""
Google Text-to-Speech Client (Mac Side)
--------------------------------------

Converts text into raw PCM audio using Google Cloud TTS.

Behavioral reference:
- tests/voice/test_voice_to_voice.py

Contract (LOCKED):
- Input: text (str)
- Output: PCM bytes (LINEAR16, 44100 Hz, mono)
- No pacing, no networking, no audio playback
"""

from collections import deque
from google.cloud import texttospeech


class GoogleTTSClient:
    """
    GoogleTTSClient wraps Google Cloud Text-to-Speech
    and returns raw PCM audio bytes.
    """

    def __init__(
        self,
        sample_rate: int = 44100,
        language_code: str = "en-US",
        voice_name: str = "en-US-Neural2-D",
    ):
        """
        Initialize the Google TTS client.

        Args:
            sample_rate (int):
                Output sample rate in Hz (must match Pi speaker)
            language_code (str):
                Language code for the voice
            voice_name (str):
                Google TTS voice name
        """
        self.sample_rate = sample_rate
        self.language_code = language_code
        self.voice_name = voice_name

        self._client = texttospeech.TextToSpeechClient()

        self._voice = texttospeech.VoiceSelectionParams(
            language_code=self.language_code,
            name=self.voice_name,
        )

        self._audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16,
            sample_rate_hertz=self.sample_rate,
        )

        # Cache for synthesized audio (FIFO with max 30 entries)
        self._cache = {}
        self._cache_keys = deque(maxlen=30)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def synthesize(self, text: str) -> bytes:
        """
        Convert text to PCM audio.

        Args:
            text (str):
                Text to synthesize.

        Returns:
            bytes:
                Raw LINEAR16 PCM audio (44100 Hz, mono).
        """
        if not text:
            return b""

        # Normalize text for cache key
        normalized_text = text.strip().lower()
        
        # Check cache
        if normalized_text in self._cache:
            return self._cache[normalized_text]

        try:
            response = self._client.synthesize_speech(
                input=texttospeech.SynthesisInput(text=text),
                voice=self._voice,
                audio_config=self._audio_config,
            )

            audio_content = response.audio_content

            # Cache the result
            if normalized_text not in self._cache:
                # Remove oldest entry if we've reached capacity and this is new
                if len(self._cache_keys) == self._cache_keys.maxlen:
                    oldest_key = self._cache_keys.popleft()
                    del self._cache[oldest_key]
                
                self._cache[normalized_text] = audio_content
                self._cache_keys.append(normalized_text)

            return audio_content

        except Exception as e:
            print(f"[TTS] Error: {e}")
            return b""
