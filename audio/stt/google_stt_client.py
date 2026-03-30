"""
Google Streaming STT Client (Mac Side)
-------------------------------------

Consumes a generator of raw PCM audio bytes and yields
FINAL transcribed text using Google Cloud Streaming STT.

Behavioral reference:
- tests/voice/test_voice_to_voice.py

Contract (LOCKED):
- Input: generator yielding PCM bytes (LINEAR16, 44100 Hz, mono)
- Output: generator yielding FINAL transcripts (str)
- Interim results are ignored
- No buffering, no retries, no audio modification
"""

import time
from typing import Generator, Iterable
from google.cloud.speech_v1.types import SpeechContext
from google.cloud import speech


class GoogleSTTClient:
    """
    GoogleSTTClient wraps Google Cloud Streaming Speech-to-Text
    and exposes a clean generator-based interface.
    """

    def __init__(
        self,
        sample_rate: int = 44100,
        language_code: str = "en-US",
    ):
        """
        Initialize the Google STT client.

        Args:
            sample_rate (int):
                Audio sample rate in Hz (must match Pi mic)
            language_code (str):
                Language code for recognition
        """
        self.sample_rate = sample_rate
        self.language_code = language_code

        self._client = speech.SpeechClient()

        self._config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=self.sample_rate,
            language_code=self.language_code,
            model="latest_long",
            speech_contexts=[
                SpeechContext(
                    phrases=["ava", "hey ava", "hi ava", "hello ava"],
                    boost=20.0,
                )
            ],
        )

        self._streaming_config = speech.StreamingRecognitionConfig(
            config=self._config,
            interim_results=True,
            single_utterance=True,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def stream_transcripts(
        self,
        audio_chunks: Iterable[bytes],
    ) -> Generator[str, None, None]:
        """
        Consume PCM audio chunks and yield FINAL transcripts.

        Args:
            audio_chunks (Iterable[bytes]):
                Generator or iterable yielding raw PCM bytes.

        Yields:
            str:
                Finalized user speech transcript.
        """
        # Convert to iterator to track exhaustion
        audio_iter = iter(audio_chunks)
        # Mutable flag to track end of audio stream
        audio_ended = {"done": False}
        stream_started = {"value": False}
        
        def request_generator():
            """
            Generator that yields audio chunks for Google STT.
            Sets audio_ended["done"] = True when audio stream ends.
            """
            try:
                for chunk in audio_iter:
                    stream_started["value"] = True
                    if chunk:  # Only yield non-empty chunks
                        yield speech.StreamingRecognizeRequest(
                            audio_content=chunk
                        )
            finally:
                # Mark audio stream as ended
                audio_ended["done"] = True

        while True:
            try:
                # Create a fresh request generator for each streaming session
                responses = self._client.streaming_recognize(
                    self._streaming_config,
                    request_generator(),
                )

                # Process responses from this streaming session
                for response in responses:
                    if not response.results:
                        continue

                    for result in response.results:
                        transcript = result.alternatives[0].transcript.strip()
                        if not transcript:
                            continue

                        # If speaking → allow interim for interruption
                        if not result.is_final:
                            yield "__INTERIM__:" + transcript
                            continue

                        # Final transcript → normal processing
                        yield transcript

                
                # Check if audio stream ended naturally
                if audio_ended["done"] and stream_started["value"]:
                    return
                
            except Exception as e:
                # Check if this is the "maximum allowed stream duration" error
                error_msg = str(e)
                if "400" in error_msg and "maximum allowed stream duration" in error_msg:
                    # Handle stream duration limit by restarting
                    print(f"[STT] Stream duration exceeded, restarting...")
                    time.sleep(0.2)
                    
                    # Only restart if audio hasn't ended
                    if audio_ended["done"]:
                        return
                    
                    # Continue while loop to restart streaming session
                    continue
                else:
                    error_msg = str(e)

                    # Handle silence timeout cleanly (no spam)
                    if "Audio Timeout" in error_msg:
                        print("[STT] Stream ended due to silence")
                        return

                    # Other STT errors
                    print(f"[STT] Error: {e}")
                    time.sleep(0.2)

                    if audio_ended["done"]:
                        return

                    continue
