"""
Mac AI Brain – Main Orchestrator
--------------------------------
Authoritative runtime entry point for voice-based intelligence.

Behavioral reference:
- tests/voice/test_voice_to_voice.py
"""

import sys
import time
import threading
import re
import os
from pathlib import Path
from enum import Enum, auto

# -------------------------------------------------------------------
# Project path setup
# -------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# -------------------------------------------------------------------
# Imports
# -------------------------------------------------------------------

from networking.tcp_server import TCPServer

from audio.audio_utils.audio_receiver import AudioReceiver
from audio.audio_utils.audio_sender import AudioSender
from audio.stt.google_stt_client import GoogleSTTClient
from audio.tts.google_tts_client import GoogleTTSClient

from intelligence.intent_classifier import IntentClassifier, Intent
from intelligence.ai_router import AIRouter
from intelligence.context_manager import ContextManager
from intelligence.guide.guide_state import GuideState
from intelligence.guide.guide_controller import GuideController
from intelligence.planner import Planner

# -------------------------------------------------------------------
# Vision
# -------------------------------------------------------------------
from vision.camera_receiver import CameraReceiver
from vision.scene_state import SceneState
from vision.perception_pipeline import PerceptionPipeline
from vision.yolo_detector import YOLODetector
from vision.vision_preview import start_preview

from utils.logger import get_logger
logger = get_logger("system", "system.log")

# -------------------------------------------------------------------
# Assistant / Executor Boundary (LOCKED)
# -------------------------------------------------------------------
# HARD RULE: This process NEVER executes physical actions.
# Executors must live in a separate system.
ENABLE_COMMAND_FORWARDING = False


# -------------------------------------------------------------------
# Brain State Machine
# -------------------------------------------------------------------

class BrainState(Enum):
    LISTENING = auto()
    PROCESSING = auto()
    SPEAKING = auto()


# -------------------------------------------------------------------
# Brain Orchestrator
# -------------------------------------------------------------------

class Brain:
    def __init__(self):
        self.state = BrainState.LISTENING
        self.running = False

        self._last_spoken_time = 0.0
        self._last_user_text = ""
        self._last_user_text_time = 0.0

        # TTS state
        self.tts_busy = False
        self.tts_lock = threading.Lock()
        self._tts_thread = None
        self._tts_stop_event = threading.Event()

        # Networking
        self.stt_server = None
        self.tts_server = None

        # Audio
        self.audio_receiver = None
        self.audio_sender = None

        # Speech
        self.stt_client = None
        self.tts_client = None

        # Intelligence
        self.intent_classifier = IntentClassifier()
        self.ai_router = AIRouter()
        self.context_manager = ContextManager()
        self.planner = Planner()
        self._last_interim_text = ""

        # ---------------------------------------------------------------
        # Vision
        # ---------------------------------------------------------------
        self.camera_receiver = None
        self.scene_state = None
        self.perception = None
        self._vision_thread = None
        self.last_detections = []

        # GUIDE
        self.guide_state = GuideState()
        self.guide_controller = GuideController(self.guide_state)

        # Wake word session state
        self.session_active = False
        self.wake_words = ("ava", "hey ava", "hello ava")
        self.closing_words = ("thanks", "thank you", "ok thanks", "okay thanks")

        # Allowed short words that should not be filtered out
        self.allowed_short_words = {
            "yes", "no", "more", "continue", "again", "repeat",
            "ok", "okay", "hi", "hey", "thanks", "thank you"
        }

    # ---------------------------------------------------------------
    # Startup
    # ---------------------------------------------------------------

    def start(self):
        logger.info("==============================")
        logger.info("Mac AI Assistant Starting")
        logger.info("==============================")


        self._start_network()
        self._start_audio()
        self._start_speech()
        self._start_vision()

        self.running = True
        self._start_vision_loop()  

        logger.info("Ready. Listening...")


    def _start_network(self):
        self.stt_server = TCPServer(port=8888)
        self.tts_server = TCPServer(port=8889)

        self.stt_server.start()
        self.tts_server.start()

        logger.info("Waiting for STT connection...")
        self.stt_server.accept()
        logger.info("STT connected")

        logger.info("Waiting for TTS connection...")
        self.tts_server.accept()
        logger.info("TTS connected")

    def _start_audio(self):
        self.audio_receiver = AudioReceiver(self.stt_server)
        self.audio_sender = AudioSender(self.tts_server)

    def _start_speech(self):
        self.stt_client = GoogleSTTClient()
        self.tts_client = GoogleTTSClient()

    # ---------------------------------------------------------------
    # Vision startup
    # ---------------------------------------------------------------

    def _start_vision(self):
        logger.info("Starting vision system...")

        self.camera_receiver = CameraReceiver(
            host="0.0.0.0",
            port=8891,
        )

        from vision.yolo_detector import YOLODetector

        self.scene_state = SceneState()

        # Create YOLO detector
        self.yolo_detector = YOLODetector(
            model_path="vision/models/yolov8n.pt"
        )

        # Create perception pipeline
        self.perception = PerceptionPipeline(
            yolo_detector=self.yolo_detector,
            scene_state=self.scene_state,
        )
        from vision.face_pipeline import FACE_PIPELINE

        FACE_PIPELINE.load_known_faces_from_photos(
            "memory/faces_photos"
        )

        logger.info("Face database loaded")


        self.camera_receiver.start()

        logger.info("Camera receiver started (port 8891)")

    def _start_vision_loop(self):
        self._vision_thread = threading.Thread(
            target=self._vision_loop,
            daemon=True,
        )
        self._vision_thread.start()
        logger.info("Vision processing thread started")

    def _vision_loop(self):
        """
        Background perception loop.
        Runs continuously without blocking voice pipeline.
        """
        logger.info("Vision loop running")

        while self.running:
            try:
                frame, ts = self.camera_receiver.get_latest_frame()

                if frame is None:
                    time.sleep(0.01)
                    continue

                # Run perception
                result = self.perception.process(frame)

                if result is not None and isinstance(result, dict):
                    if hasattr(self.scene_state, "update"):
                        self.scene_state.update(result)
                    elif hasattr(self.scene_state, "update_from_perception"):
                        self.scene_state.update_from_perception(result)
                        
                    self.last_detections = result.get("objects", [])
                    
            except Exception as e:
                logger.exception(f"Vision loop error: {e}")
                time.sleep(0.1)
                
    # ---------------------------------------------------------------
    # Vision → text summary
    # ---------------------------------------------------------------
    def _get_scene_summary(self) -> str:
        """
        Convert SceneState into a short natural summary for the AI.
        Safe, fast, and optional.
        """
        try:
            if not self.scene_state:
                return ""

            objects = getattr(self.scene_state, "objects", [])
            people = getattr(self.scene_state, "people", [])
            person_visible = getattr(self.scene_state, "person_visible", False)

            parts = []

            # Person info (highest priority)
            if person_visible:
                if people:
                    names = [p.get("name", "person") for p in people]
                    parts.append(f"Person detected: {', '.join(names)}")
                else:
                    parts.append("Person detected")

            # Object summary (limit to avoid prompt spam)
            if objects:
                labels = [o.get("label", "") for o in objects[:5] if o.get("label")]
                if labels:
                    parts.append(f"Objects visible: {', '.join(labels)}")

            if not parts:
                return "No significant objects detected"

            return " | ".join(parts)

        except Exception as e:
            logger.debug(f"Scene summary error: {e}")
            return ""


    # ---------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------

    def _is_stop_command(self, text: str) -> bool:
        stops = {"stop", "cancel", "quiet", "pause", "shut up"}
        t = text.strip().lower()
        return any(s in t for s in stops)

    def _should_ignore_transcript(self, text: str) -> bool:
        """
        Determine if a transcript should be ignored before processing.
        Returns True if the transcript is likely noise or an incomplete fragment.
        """

        if self.tts_busy:
            return True

        t = text.strip().lower()
        if not t:
            return True

        # Never ignore stop commands
        if self._is_stop_command(text):
            return False

        # If guide is active, ignore certain auto-prompts
        if self.guide_controller.is_active():
            auto_phrases = [
                "should i continue",
                "do you want me to continue",
                "shall i continue",
            ]
            if any(p in t for p in auto_phrases):
                return True

        # Check word count
        words = t.split()
        word_count = len(words)

        # Very short utterances: ignore unless they are allowed
        if word_count <= 2:
            # Allow specific short responses
            if t in self.allowed_short_words:
                return False
            # Also allow single words that might be wake words (but wake word already handled)
            return True

        # Check for dangling fragments that are too incomplete
        dangling_patterns = [
            r'^tell me$',
            r'^tell me about$',
            r'^what is$',
            r'^what are$',
            r'^he has$',
            r'^she has$',
            r'^it is$',
            r'^i am$',
            r'^i\'m$',
            r'^can you$',
            r'^could you$',
            r'^how to$',
            r'^how do I$',
        ]
        for pattern in dangling_patterns:
            if re.match(pattern, t):
                return True

        return False

    def _contains_wake_word(self, text: str) -> bool:
        t = text.lower()
        return any(re.search(rf"\b{re.escape(w)}\b", t) for w in self.wake_words)

    def _contains_closing_intent(self, text: str) -> bool:
        t = text.lower()
        # closing only if at END of sentence
        for word in self.closing_words:
            if t.endswith(word):
                return True
        return False

    # ---------------------------------------------------------------
    # Interruptible TTS
    # ---------------------------------------------------------------

    def _set_tts_busy(self, value: bool):
        with self.tts_lock:
            self.tts_busy = value

    def _split_into_chunks(self, text: str):
        parts = re.split(r'(?<=[.!?])\s+|(?<=,)\s+|(?<=;)\s+|(?<=:)\s+', text)
        return [p.strip()[:160] for p in parts if p.strip()]

    def _tts_worker(self, text: str):
        try:
            for chunk in self._split_into_chunks(text):

                if self._tts_stop_event.is_set():
                    return
                
                time.sleep(0)

                pcm = self.tts_client.synthesize(chunk)

                if self._tts_stop_event.is_set():
                    return

                self.audio_sender.stream_paced(pcm)

                if self._tts_stop_event.is_set():
                    return

        finally:
            self._set_tts_busy(False)
            self.state = BrainState.LISTENING

    def _speak_interruptible(self, text: str):
        if self._tts_thread and self._tts_thread.is_alive():
            self._tts_stop_event.set()
            self._tts_thread.join(timeout=1.0)

        self._tts_stop_event.clear()
        self._set_tts_busy(True)
        self.state = BrainState.SPEAKING

        time.sleep(0.01)  # tiny guard for smoother audio start

        self._tts_thread = threading.Thread(
            target=self._tts_worker,
            args=(text,),
            daemon=True,
        )
        self._tts_thread.start()

    # ---------------------------------------------------------------
    # Main Loop
    # ---------------------------------------------------------------

    def run(self):
        if not self.running:
            raise RuntimeError("Assistant not started")

        try:
            while self.running:

                print("[STT] Waiting for speech...")

                # Block until first audio chunk arrives
                audio_gen = self.audio_receiver.audio_chunks()
                first_chunk = next(audio_gen, None)

                if first_chunk is None:
                    time.sleep(0.1)
                    continue

                print("[STT] Audio detected. Starting STT session...")

                # Recreate generator including first chunk
                def combined_audio():
                    yield first_chunk
                    for chunk in audio_gen:
                        yield chunk

                try:
                    for text in self.stt_client.stream_transcripts(combined_audio()):

                        if not self.running:
                            break

                        if not text:
                            continue

                        # Handle interim transcripts (for early barge-in)
                        if text.startswith("__INTERIM__:"):
                            interim_text = text.replace("__INTERIM__:", "").strip().lower()
                            # suppress duplicate interim spam
                            if interim_text != self._last_interim_text:
                                print("INTERIM:", interim_text)
                                self._last_interim_text = interim_text

                            # 🚨 EARLY BARGE-IN (aggressive & natural)
                            if self.tts_busy:
                                # Ignore very tiny noise
                                if len(interim_text.strip()) >= 1:
                                    print("[EARLY BARGE-IN] Interrupting TTS (speech detected)")

                                    self._tts_stop_event.set()

                                    if self.audio_sender:
                                        self.audio_sender.hard_stop()
                                        self._set_tts_busy(False)
                                        time.sleep(0.02)

                                    self.state = BrainState.LISTENING
                            continue

                        # FINAL transcripts
                        print("FINAL:", text)

                        clean_text = text.strip().lower()

                        # --------------------------------
                        # 1. If session NOT active → wait for wake word
                        # --------------------------------
                        if not self.session_active:
                            if self._contains_wake_word(clean_text):
                                print("[WAKE] Wake word detected")
                                self.session_active = True

                                # Remove wake word from command
                                for w in self.wake_words:
                                    clean_text = clean_text.replace(w, "").strip()

                                if not clean_text:
                                    # User only said wake word → add small delay for smoothness
                                    time.sleep(0.12)
                                    self._speak_interruptible("Yes, how can I help?")
                                    continue
                            else:
                                # Ignore everything until wake word
                                continue

                        # --------------------------------
                        # 2. If session active → let AI handle closings naturally
                        #    (no special handling here; will be processed in _handle_user_text)
                        # --------------------------------

                        # If user speaks while TTS is active → immediate barge-in
                        if self.tts_busy:
                            if len(clean_text.strip()) >= 2:
                                print("[BARGE-IN] User interrupted speech")

                                self._tts_stop_event.set()

                                if self.audio_sender:
                                    self.audio_sender.hard_stop()
                                    self._set_tts_busy(False)
                                    time.sleep(0.03)

                                self.state = BrainState.LISTENING
                            else:
                                # Ignore tiny noise
                                continue

                        # Filter out incomplete/noisy transcripts
                        if self._should_ignore_transcript(clean_text):
                            print("[FILTER] Ignoring transcript:", clean_text)
                            continue

                        # Process user command
                        self._handle_user_text(clean_text)

                except Exception as e:
                    import traceback
                    print("[STT] Exception occurred:")
                    traceback.print_exc()
                    self.state = BrainState.LISTENING
                    time.sleep(0.2)
                    continue

        except KeyboardInterrupt:
            logger.warning("Interrupted by user")

        finally:
            self.stop()

    # ---------------------------------------------------------------
    # Text Handling
    # ---------------------------------------------------------------

    def _handle_user_text(self, text: str):
        logger.info(f"USER: {text}")
        print("HANDLE:", text)

        # small grammar normalization
        if text.startswith("we are complete this sentence"):
            text = "complete this sentence"

        self.state = BrainState.PROCESSING
        
        intent, confidence = self.intent_classifier.classify(text)
        # Fix: treat common small-talk as chat
        small_talk = {
            "how are you",
            "how are you doing",
            "what's up",
            "how are things"
        }

        if text in small_talk:
            intent = Intent.CHAT

        self.context_manager.add_user_message(text)

        context_text = self.context_manager.get_context()

        # ---------------------------------------------------------------
        # Inject vision awareness (SAFE)
        # ---------------------------------------------------------------
        scene_summary = self._get_scene_summary()
        if scene_summary:
            context_text = f"[VISION] {scene_summary}\n\n" + context_text


        decision = self.planner.decide(
            user_text=text,
            intent=intent,
            confidence=confidence,
            context=context_text,
        )

        # ---------------------------------------------------------------
        # Explicit command forwarding guard (STEP 4)
        # ---------------------------------------------------------------
        if intent == Intent.COMMAND and not ENABLE_COMMAND_FORWARDING:
            logger.info("Command detected but forwarding is disabled (assistant-only mode)")
            decision.response.speech = (
                "I can understand movement-related requests, "
                "but I can’t perform physical actions. "
                "Could you clarify what you’d like help with?"
            )

        # If planner already generated a terminal response for incomplete input,
        # do NOT call AI router again.
        if decision.response and decision.response.speech:
            # Incomplete input case (GUIDE mode)
            if decision.reason == "incomplete_input":
                self._speak_interruptible(decision.response.speech)
                self.context_manager.add_ai_message(decision.response.speech)
                self.state = BrainState.LISTENING
                return

            # For all other reasons (greeting, polite_closure, etc.), let AI generate response
            # (do not return early)

        # Generate AI response
        response = self.ai_router.generate_response(
            user_text=text,
            intent=intent,
            context=context_text,
        )

        if response:
            logger.info(f"AI: {response}")
            self._speak_interruptible(response)
            self.context_manager.add_ai_message(response)

        # If the user said a closing phrase, end the session after AI response
        if self._contains_closing_intent(text):
            self.session_active = False
            self.tts_server.send(b"__SESSION_END__")
            logger.info("Session ended due to closing intent")

        self.state = BrainState.LISTENING

    # ---------------------------------------------------------------
    # Shutdown
    # ---------------------------------------------------------------

    def stop(self):
        if not self.running:
            return

        logger.info("Shutting down...")
        self.running = False

        self._tts_stop_event.set()
        if self._tts_thread and self._tts_thread.is_alive():
            self._tts_thread.join(timeout=1.0)

        try:
            if self.stt_server:
                self.stt_server.close()
            if self.tts_server:
                self.tts_server.close()
        except Exception:
            pass

        logger.info("Shutdown complete")


# -------------------------------------------------------------------
# Entry Point
# -------------------------------------------------------------------

def main():
    import threading
    from vision.vision_preview import start_preview

    brain = Brain()
    brain.start()

    # Run brain in background thread
    brain_thread = threading.Thread(
        target=brain.run,
        daemon=True,
    )
    brain_thread.start()

    # Run preview in MAIN thread (macOS requirement)
    stop_event = threading.Event()

    try:
        start_preview(brain)
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        brain.stop()



if __name__ == "__main__":
    main()
