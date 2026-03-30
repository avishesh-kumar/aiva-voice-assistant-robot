"""
Mac AI Brain – Main Orchestrator
--------------------------------
Authoritative runtime entry point for voice-based intelligence.

Behavioral reference:
- tests/voice/test_voice_to_voice.py
"""

import sys
import time
import signal
import threading
import re
import os
from pathlib import Path
import cv2
from enum import Enum, auto
from google.genai import types

# -------------------------------------------------------------------
# Project path setup
# -------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# -------------------------------------------------------------------
# Imports
# -------------------------------------------------------------------

from networking.tcp_server import TCPServer
from utils.logger import setup_logger
logger = setup_logger("BRAIN", log_file="system.log")

from audio.audio_utils.audio_receiver import AudioReceiver
from audio.audio_utils.audio_sender import AudioSender
from scripts.vision_preview import start_preview
from audio.stt.google_stt_client import GoogleSTTClient
from audio.tts.google_tts_client import GoogleTTSClient

from intelligence.intent_classifier import IntentClassifier, Intent
from intelligence.ai_router import AIRouter
from intelligence.context_manager import ContextManager

from networking.command_client import CommandClient
from intelligence.planner import Planner
from config.features import ENABLE_SCENE_QA
from intelligence.intent_classifier import Intent
from vision.scene_state import SceneState
from vision.camera_receiver import CameraReceiver
from vision.yolo_detector import YOLODetector
from behaviors.go_to_object import go_to_object_loop

# Try to import Gemini client
try:
    from google import genai
    from google.genai import types
    GEMINI_AVAILABLE = True
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
    if not GOOGLE_API_KEY:
        logger.warning("GOOGLE_API_KEY not set. Scene questions will not work")
        GEMINI_AVAILABLE = False
except ImportError:
    GEMINI_AVAILABLE = False
    GOOGLE_API_KEY = None

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
        
        self._last_safety_message = ""
        self._last_safety_message_time = 0.0

        # TTS busy state
        self.tts_busy = False
        self.tts_lock = threading.Lock()
        self._stop_tts_flag = False
        
        # Stop speaking flag
        self.stop_speaking = False
        
        # Non-blocking TTS thread management
        self._tts_thread = None
        self._tts_stop_event = threading.Event()
        self._tts_queue_lock = threading.Lock()

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
        self._gemini_cooldown_until = 0.0
        self.planner = Planner()
        self.preview_stop_event = threading.Event()
        
        self._speech_active = False
        self._paused_behavior = None
        self._obstacle_blocked = False
        self._last_scene_time = 0.0

        # ---------------- IMU STATE ----------------
        self.latest_imu = {
            "x": 0.0,
            "y": 0.0,
            "z": 0.0,
            "timestamp": 0.0,
        }


        # Gemini client for scene questions
        if GEMINI_AVAILABLE and GOOGLE_API_KEY:
            try:
                self.gemini_client = genai.Client(api_key=GOOGLE_API_KEY)
                logger.info("Gemini client initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini client: {e}")
                self.gemini_client = None
        else:
            self.gemini_client = None
            if not GEMINI_AVAILABLE:
                logger.warning("google-genai package not available. Scene questions will not work")
            elif not GOOGLE_API_KEY:
                logger.warning("GOOGLE_API_KEY not set. Scene questions will not work")

        # Command client for Pi control
        pi_ip = os.getenv("PI_IP", "10.75.252.75")
        self.command_client = CommandClient(host=pi_ip, port=8890)

        # Vision
        self.camera_receiver = CameraReceiver(host="0.0.0.0", port=8891)
        self._last_vision_status_time = 0.0
        
        # YOLO
        self.yolo = YOLODetector()
        self.last_detections = []
        self.last_detection_time = 0.0
        self._yolo_thread = None
        self._last_yolo_summary_time = 0.0
        # Scene state (shared world model for autonomy)
        from vision.scene_state import SceneState
        self.scene_state = SceneState(frame_width=640)
        
        from behaviors.behavior_manager import BehaviorManager
        self.behavior_manager = BehaviorManager()

        from vision.perception_pipeline import PerceptionPipeline
        self.perception = PerceptionPipeline(self.yolo, self.scene_state)

        self._final_speech_time = 0.0

    # ---------------------------------------------------------------
    # TTS Busy State Management
    # ---------------------------------------------------------------

    def _set_tts_busy(self, value: bool):
        with self.tts_lock:
            self.tts_busy = value

    # ---------------------------------------------------------------
    # Startup
    # ---------------------------------------------------------------

    def start(self):
        logger.info("==============================")
        logger.info("Mac AI Brain starting")
        logger.info("==============================")


        self._start_network()
        self._start_audio()
        self._start_speech()
        self._start_vision()
        self.running = True
        self._start_yolo()
        # Start background status polling (IMU + safety)
        t = threading.Thread(
            target=self._status_poll_loop,
            daemon=True
        )
        t.start()


        logger.info("System ready. Listening")

    def _wait_for_client(self, server: TCPServer, label: str):
        """
        Block until a TCP client connects and is accepted.
        """
        logger.info(f"Waiting for {label} connection")

        # Explicitly accept client if not already accepted
        while getattr(server, "_client_socket", None) is None:
            try:
                server.accept_client()
            except BlockingIOError:
                pass
            except Exception:
                pass

            time.sleep(0.05)

        logger.info(f"{label} connected")



    def _start_network(self):
        # Create servers
        self.stt_server = TCPServer(port=8888)
        self.tts_server = TCPServer(port=8889)

        # Start listening
        self.stt_server.start()
        self.tts_server.start()

        logger.info("Waiting for STT connection")
        self.stt_server.accept()   # BLOCKS until Pi connects
        logger.info("STT connected")

        logger.info("Waiting for TTS connection")
        self.tts_server.accept()   # BLOCKS until Pi connects
        logger.info("TTS connected")

        # Connect to Pi command server
        logger.info("Connecting to command server")
        try:
            self.command_client.connect()
            logger.info("Command server connected")
        except Exception as e:
            logger.warning(f"Command server connection failed: {e}")

    def _start_audio(self):
        self.audio_receiver = AudioReceiver(self.stt_server)
        self.audio_sender = AudioSender(self.tts_server)

    def _start_speech(self):
        self.stt_client = GoogleSTTClient()
        self.tts_client = GoogleTTSClient()

    def _start_vision(self):
        """Start camera receiver + live preview"""

        # Start camera receiver
        t = threading.Thread(
            target=self.camera_receiver.start,
            daemon=True
        )
        t.start()
        logger.info("Camera receiver started on port 8891")

        # Stop event for preview window
        self.preview_stop_event = threading.Event()

        logger.info("Live camera preview started")
        # ⏳ Wait for first camera frame
        while self.camera_receiver.get_latest_frame()[0] is None:
            time.sleep(0.05)

        # 🟢 Load known faces from photos (ONCE)
        from vision.face_pipeline import FACE_PIPELINE
        FACE_PIPELINE.load_known_faces_from_photos(
            "memory/faces_photos"
        )


    def _start_yolo(self):
        """Start YOLO detection in background thread"""
        self._yolo_thread = threading.Thread(target=self._vision_yolo_loop, daemon=True)
        self._yolo_thread.start()
        logger.info("YOLO detection thread started")

    # ---------------------------------------------------------------
    # YOLO Detection Loop
    # ---------------------------------------------------------------

    def _vision_yolo_loop(self):
        """Background thread for YOLO detection at 2 FPS"""
        detection_interval = 0.2
        
        while not self.running:
            time.sleep(0.1)  # Wait for brain to start
        
        while self.running:
            try:
                # Get latest frame
                frame, frame_time = self.camera_receiver.get_latest_frame()
                # Cache latest frame for scene understanding (LLaVA / Gemini)
                self.latest_frame = frame

                
                if frame is None:
                    time.sleep(detection_interval)
                    continue
                if not getattr(self.yolo, "model_loaded", False):
                    time.sleep(2.0)
                    continue
                # Update scene frame width dynamically (first valid frame)
                h, w = frame.shape[:2]
                self.scene_state.frame_width = w


                depth_map = self.perception.process(frame)
                self.last_detections = self.scene_state.objects
                self.last_detection_time = time.time()
            
                # Print summary every 2 seconds
                current_time = time.time()
                if current_time - self._last_yolo_summary_time >= 2.0:
                    current_objects = self.scene_state.objects

                    if current_objects:
                        summary = {}
                        for obj in current_objects:
                            label = obj.get("label")
                            summary[label] = summary.get(label, 0) + 1

                        summary_str = ",".join([f"{k}:{v}" for k, v in summary.items()])
                        logger.debug(f"YOLO detections: {{{summary_str}}}")
                    else:
                        logger.debug("YOLO: no detections")

                    self._last_yolo_summary_time = current_time

                
                # Sleep to maintain 2 FPS
                time.sleep(detection_interval)
                
            except Exception as e:
                logger.exception("YOLO detection loop error")
                time.sleep(1.0)  # Avoid tight loop on error


    def _extract_enrollment_name(self, text: str) -> str | None:
        """
        Extract a person's name from enrollment command.
        Examples:
          'remember Avi'
          'register Rahul'
          'save my face as John'
        """
        text = text.lower()

        patterns = [
            r"remember (.+)",
            r"register (.+)",
            r"enroll (.+)",
            r"save (?:my face )?as (.+)",
        ]

        for p in patterns:
            m = re.search(p, text)
            if m:
                name = m.group(1).strip()
                if name:
                    return name.title()

        return None

    # ---------------------------------------------------------------
    # Vision Question Detection
    # ---------------------------------------------------------------

    '''def _is_vision_question(self, text: str) -> bool:
        if not text:
            return False

        normalized = text.strip().lower()

        # 🚫 If this is a movement command, DO NOT treat as vision question
        movement_verbs = ["go", "move", "come", "follow", "walk", "approach"]
        if any(v in normalized for v in movement_verbs):
            return False

        question_triggers = [
            "what do you see",
            "what can you see",
            "what is there",
            "is there",
            "are there",
            "how many",
            "do you see",
            "can you see",
            "count",
        ]

        return any(trigger in normalized for trigger in question_triggers)'''

    '''def _answer_from_yolo(self, text: str) -> str:
        """
        Generate an answer based on YOLO detections.
        """
        # Check if detections are recent (within 2 seconds)
        current_time = time.time()
        if current_time - self.last_detection_time > 2.0:
            return "I can't see clearly right now."
            
        if not self.last_detections:
            return "I don't see any objects right now."
        
        # Build counts per label
        counts = {}
        for detection in self.last_detections:
            label = detection["label"]
            counts[label] = counts.get(label, 0) + 1
        
        # Handle specific queries
        normalized = text.strip().lower()
        
        # Count people
        if "how many people" in normalized or "count people" in normalized:
            people_count = counts.get("person", 0)
            if people_count == 0:
                return "I don't see any people."
            elif people_count == 1:
                return "I see one person."
            else:
                return f"I see {people_count} people."
        
        # Check for specific object
        for obj in ["bottle", "chair", "table", "car", "cat", "dog"]:
            if obj in normalized or f"is there a {obj}" in normalized:
                obj_count = counts.get(obj, 0)
                if obj_count > 0:
                    return f"Yes, I see {obj_count} {obj}{'s' if obj_count > 1 else ''}."
                else:
                    return f"No, I don't see any {obj}s."
        
        # General description - Improved natural language
        if counts:
            items = []
            for label, count in counts.items():
                if count == 1:
                    items.append(f"a {label}")
                else:
                    items.append(f"{count} {label}s")
            
            if len(items) == 1:
                return f"I see {items[0]}."
            elif len(items) == 2:
                return f"I see {items[0]} and {items[1]}."
            else:
                return f"I see {', '.join(items[:-1])}, and {items[-1]}."
        
        return "I don't see any objects right now."'''

    # ---------------------------------------------------------------
    # Scene Question Detection
    # ---------------------------------------------------------------

    '''def _is_scene_question(self, text: str) -> bool:
        """
        Detect if the user is asking about the scene or environment.
        """
        if not text:
            return False
            
        normalized = text.strip().lower()
        
        scene_keywords = [
            "describe the room",
            "describe the surrounding",
            "describe surroundings",
            "tell me about the surrounding",
            "tell me about surroundings",
            "describe the surroundings",
            "describe the scene",
            "describe the place",
            "describe environment",
            "describe the environment",
        ]
        
        for keyword in scene_keywords:
            if keyword in normalized:
                return True
                
        return False'''

    def _handle_scene_query(self, text: str) -> str:
        # --- SAFETY CHECK ---
        from config.features import ENABLE_SCENE_QA
        if not ENABLE_SCENE_QA:
            return "Scene understanding is currently disabled."

        # --- GET SHARED PERCEPTION STATE ---
        # This does NOT trigger any detection, it only reads cached results
        scene_state = self.scene_state

        print("\n[DEBUG][SCENE_STATE PEOPLE]")
        for i, p in enumerate(scene_state.people):
            print(
                f"Person {i}: "
                f"name={p.get('name')}, "
                f"emotion={p.get('emotion')}, "
                f"emotion_conf={p.get('emotion_conf')}, "
                f"confidence={p.get('confidence')}"
            )
        print(f"Total people detected: {len(scene_state.people)}\n")


        # ======================================================
        # GEMINI SCENE DESCRIPTION (DESCRIBE QUERIES ONLY)
        # ======================================================
        describe_keywords = [
            "describe",
            "described",
            "room",
            "scene",
            "surroundings",
            "environment",
        ]

        text_l = text.lower()

        if any(k in text_l for k in describe_keywords):
            if self.gemini_client:
                try:
                    gemini_text = self._answer_scene_from_gemini(text)
                    if gemini_text:
                        return gemini_text
                except Exception as e:
                    logger.warning(f"Gemini failed, using local fallback: {e}")

        people = getattr(scene_state, "people", [])
        objects = getattr(scene_state, "objects", [])
        print("[DEBUG][SCENE_STATE OBJECTS]")
        for obj in objects:
            print(f"Object: label={obj.get('label')}, conf={obj.get('confidence')}")
        print()


        response_parts = []

        # ======================================================
        # PEOPLE + EMOTION (FACE RECOGNITION OUTPUT)
        # ======================================================
        total_people = len(scene_state.person_boxes)
        people = scene_state.people or []

        if total_people > 0:
            response_parts.append(f"I see {total_people} people.")

            # Speak recognized people
            for p in people:
                name = p.get("name") or "an unknown person"

                sentence = f"I see {name}"

                emo_conf = p.get("emotion_conf", 0)
                if emo_conf >= 0.6:
                    emotion = p.get("emotion", "")
                    if emotion:
                        sentence += f" who looks {emotion}"

                response_parts.append(sentence + ".")

            # Add unknown persons not recognized
            unknown_count = total_people - len(people)
            for _ in range(max(0, unknown_count)):
                response_parts.append("I see an unknown person.")

        else:
            response_parts.append("I don't see any people right now.")


        # ======================================================
        # OBJECTS (YOLO OUTPUT)
        # ======================================================
        object_counts = {}
        for obj in objects:
            label = obj.get("label")
            if not label or label == "person":
                continue
            object_counts[label] = object_counts.get(label, 0) + 1

        if object_counts:
            object_phrases = []
            for label, count in object_counts.items():
                if count == 1:
                    object_phrases.append(f"a {label}")
                else:
                    object_phrases.append(f"{count} {label}s")

            if len(object_phrases) == 1:
                response_parts.append(f"I also see {object_phrases[0]}.")
            elif len(object_phrases) == 2:
                response_parts.append(
                    f"I also see {object_phrases[0]} and {object_phrases[1]}."
                )
            else:
                response_parts.append(
                    "I also see " +
                    ", ".join(object_phrases[:-1]) +
                    f", and {object_phrases[-1]}."
                )

        if response_parts:
            return " ".join(response_parts)

        return self._strict_yolo_scene_summary()


    def _fallback_scene_from_yolo(self) -> str:
        scene_state = self.scene_state
        parts = []

        # ---------- PEOPLE ----------
        if scene_state.people:
            for p in scene_state.people:
                name = p.get("name", "a person")
                if p.get("confidence", 0) < 0.6:
                    name = "a person"

                sentence = f"I see {name}"

                emo = p.get("emotion")
                emo_conf = p.get("emotion_conf", 0)
                if emo and emo_conf >= 0.6:
                    sentence += f" who looks {emo}"

                # VERY SAFE posture hint
                bbox = p.get("bbox")
                if bbox:
                    x, y, w, h = bbox
                    if h > w * 1.4:
                        sentence += ", standing"
                    elif w > h:
                        sentence += ", possibly sitting"

                parts.append(sentence + ".")

        else:
            parts.append("I do not see any people.")

        # ---------- OBJECTS ----------
        counts = {}
        for obj in scene_state.objects:
            label = obj.get("label")
            if not label or label == "person":
                continue
            counts[label] = counts.get(label, 0) + 1

        if counts:
            obj_phrases = []
            for k, v in counts.items():
                obj_phrases.append(f"{v} {k}" if v > 1 else f"a {k}")
            parts.append("I can also see " + ", ".join(obj_phrases) + ".")
        else:
            parts.append("I do not see any clear objects nearby.")

        # ---------- ENVIRONMENT ----------
        parts.append("The surroundings are partially visible, but details are limited without deeper visual analysis.")

        return " ".join(parts)

    def _strict_yolo_scene_summary(self) -> str:

        scene_state = self.scene_state

        print("\n[DEBUG][STRICT_YOLO_SUMMARY]")
        print(f"People count (YOLO): {len(scene_state.person_boxes)}")
        print(f"Known faces: {len(scene_state.people)}")

        for p in scene_state.people:
            print(
                f"Person: name={p.get('name')}, "
                f"emotion={p.get('emotion')}, "
                f"emotion_conf={p.get('emotion_conf')}"
            )

        print("Objects:")
        for obj in scene_state.objects:
            print(f" - {obj.get('label')}")
        print()
        
        parts = []

        # ---------- PEOPLE ----------
        people = scene_state.people or []
        person_boxes = scene_state.person_boxes or []
        count = len(person_boxes)

        parts.append(f"I see {count} person{'s' if count != 1 else ''}.")

        used = set()

        for p in people:
            name = p.get("name") or "unknown person"
            used.add(name)

            sentence = name
            emo = p.get("emotion")
            emo_conf = p.get("emotion_conf", 0)
            if emo and emo_conf >= 0.6:
                sentence += f" who looks {emo}"

            parts.append(sentence + ".")

        # Add unknown people for unmatched YOLO persons
        unknown_count = max(0, count - len(used))
        for _ in range(unknown_count):
            parts.append("unknown person.")


        # ---------- OBJECTS ----------
        objects = scene_state.objects or []
        counts = {}

        for obj in objects:
            label = obj.get("label")
            if not label or label == "person":
                continue
            counts[label] = counts.get(label, 0) + 1

        if counts:
            obj_parts = []
            for label, cnt in counts.items():
                if cnt == 1:
                    obj_parts.append(f"a {label}")
                else:
                    obj_parts.append(f"{cnt} {label}s")

            parts.append("I also see " + ", ".join(obj_parts) + ".")

        return " ".join(parts)


    
    def _build_local_scene_summary(self) -> str:
        scene_state = self.scene_state

        lines = []

        # ---------- PEOPLE ----------
        if scene_state.people:
            for p in scene_state.people:
                name = p.get("name", "a person")
                if p.get("confidence", 0) < 0.6:
                    name = "a person"

                sentence = name

                emo = p.get("emotion")
                emo_conf = p.get("emotion_conf", 0)
                if emo and emo_conf >= 0.6:
                    sentence += f" who looks {emo}"

                lines.append(sentence)
        else:
            lines.append("no people detected")

        # ---------- OBJECTS ----------
        counts = {}
        for obj in scene_state.objects:
            label = obj.get("label")
            if not label or label == "person":
                continue
            counts[label] = counts.get(label, 0) + 1

        if counts:
            obj_parts = []
            for k, v in counts.items():
                obj_parts.append(f"{v} {k}" if v > 1 else f"a {k}")
            lines.append("objects visible: " + ", ".join(obj_parts))
        else:
            lines.append("no clear objects detected")

        return "; ".join(lines)


    def _answer_scene_from_gemini(self, text: str) -> str:
        """
        Generate an answer using Gemini Flash vision for scene description.
        """
        if time.time() - self._last_scene_time < 5.0 and hasattr(self, "_last_scene_text"):
            return self._last_scene_text

        self._last_scene_time = time.time()

        if not self.gemini_client:
            return self._strict_yolo_scene_summary()
        if time.time() < self._gemini_cooldown_until:
            return self._strict_yolo_scene_summary()
        if time.time() - self.last_detection_time > 2.0 and not self.last_detections:
            return "I can't describe the room clearly right now. Please move the camera slowly and try again."
        
        # Get latest frame
        frame, frame_time = self.camera_receiver.get_latest_frame()
        
        if frame is None:
            return "Camera is not ready right now."
        
        # Check if frame is too old (>2 seconds)
        current_time = time.time()
        if current_time - frame_time > 2.0:
            return "Camera is not ready right now."
        yolo_hint = "YOLO detected: none"
        try:
            if self.last_detections and (time.time() - self.last_detection_time) < 2.0:
                summary = self.yolo.summarize(self.last_detections)
                if summary:
                    summary_str = ", ".join([f"{k}:{v}" for k, v in summary.items()])
                    yolo_hint = f"YOLO detected (may be incomplete): {summary_str}"
        except Exception:
            pass

        try:
            # Convert frame to JPEG bytes for Gemini API
            import cv2
            # Wait briefly for a fresh frame (up to 0.4s)
            start_wait = time.time()
            while time.time() - start_wait < 0.4:
                frame2, frame_time2 = self.camera_receiver.get_latest_frame()
                if frame2 is not None and (time.time() - frame_time2) < 0.25:
                    frame, frame_time = frame2, frame_time2
                    break
                time.sleep(0.03)

            # Encode frame as JPEG
            success, encoded_image = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
            if not success:
                return "I had trouble processing the camera image."
            
            jpg_bytes = encoded_image.tobytes()
            
            # Create image part
            img = types.Part.from_bytes(data=jpg_bytes, mime_type="image/jpeg")

            # Use Gemini to describe the scene with improved prompt
            people_desc = []
            for p in self.scene_state.people:
                name = p.get("name", "unknown person")
                if p.get("confidence", 0) < 0.6:
                    name = "unknown person"

                emo = p.get("emotion")
                emo_conf = p.get("emotion_conf", 0)
                if emo and emo_conf >= 0.6:
                    people_desc.append(f"{name} looks {emo}")
                else:
                    people_desc.append(f"{name} (emotion unclear)")

            total_people = len(self.scene_state.person_boxes)
            known = len(people_desc)

            if total_people > known:
                people_desc.append(f"{total_people - known} unknown person")

            people_hint = ", ".join(people_desc) if people_desc else "No people detected"

            objects_desc = []
            summary = self.yolo.summarize(self.last_detections) if self.last_detections else {}
            for k, v in summary.items():
                objects_desc.append(f"{v} {k}" if v > 1 else f"a {k}")

            objects_hint = ", ".join(objects_desc) if objects_desc else "No clear objects detected"



            print("\n[DEBUG][GEMINI INPUT]")
            print("People hint:", people_hint)
            print("Objects hint:", objects_hint)
            print()

            prompt = f"""
            You are a robot describing its surroundings using real perception data.

            RULES:
            - Do NOT guess.
            - Do NOT invent objects.
            - Mention people ONLY if visible.
            - Mention emotions ONLY if provided.
            - You MUST write at least 3 complete sentences.
            - NEVER stop mid-sentence.
            - If unsure, still complete the sentence clearly.


            Known people and emotions:
            {people_hint}

            Detected objects:
            {objects_hint}

            User request:
            {text}
            """

            if len(text.split()) < 3:
                return self._strict_yolo_scene_summary()

            # Call Gemini API with corrected SDK call
            response = self.gemini_client.models.generate_content(
                model="models/gemini-2.5-flash",
                contents=[
                    types.Content(
                        role="user",
                        parts=[
                            img,
                            types.Part.from_text(text=prompt),
                        ],
                    )
                ],
                config=types.GenerateContentConfig(
                    max_output_tokens=400,
                    temperature=0.4,
                ),
            )
            
            scene_text = response.text.strip() if response and response.text else ""
            # Clean up line endings so TTS doesn't cut awkwardly
            lines = []
            for ln in scene_text.splitlines():
                ln = ln.strip()
                if not ln:
                    continue

                # remove bullet markers
                if ln.startswith("*"):
                    ln = ln.lstrip("*").strip()
                if ln.startswith("-"):
                    ln = ln.lstrip("-").strip()

                # remove trailing dots/spaces
                ln = ln.rstrip()

                lines.append(ln)

            scene_text = ". ".join(lines)
            # Enforce minimum sentence count (Gemini may stop early)
            sentences = [s.strip() for s in scene_text.split(".") if s.strip()]
            if len(sentences) < 3:
                return self._strict_yolo_scene_summary()

            # Reject semantically incomplete endings
            BAD_ENDINGS = (
                " is on.",
                " is",
                " are",
                " with.",
                " of.",
                " near.",
                " a.",
                " an.",
            )


            if any(scene_text.endswith(bad) for bad in BAD_ENDINGS):
                return self._strict_yolo_scene_summary()

            if scene_text and not scene_text.endswith((".", "!", "?")):
                scene_text += "."
            
            # If Gemini returns empty, fallback to YOLO
            if not scene_text:
                return self._strict_yolo_scene_summary()

            self._last_scene_text = scene_text
            return scene_text

            
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                # default cooldown
                cooldown = 60

                # try to extract "retry in XXs" from error message
                m = re.search(r"retry in ([0-9]+)", str(e).lower())
                if m:
                    cooldown = int(m.group(1)) + 2  # add small buffer

                self._gemini_cooldown_until = time.time() + cooldown

            logger.warning("Gemini quota hit (429). Using YOLO fallback")
            # Fallback to YOLO if Gemini fails
            return self._strict_yolo_scene_summary()


    def _status_poll_loop(self):
        """Continuously poll status messages from Pi (IMU, safety, etc)."""
        logger.info("Status poll thread started")

        while self.running:
            try:
                self._handle_safety_feedback()
            except Exception as e:
                logger.debug(f"Status poll error: {e}")

            time.sleep(0.05)  # 20 Hz polling (safe & light)

    
    # ---------------------------------------------------------------
    # Vision Status Monitoring
    # ---------------------------------------------------------------

    def _print_vision_status(self):
        """Print vision status every 5 seconds"""
        current_time = time.time()
        if current_time - self._last_vision_status_time >= 5.0:
            if self.camera_receiver.frames_received > 0:
                age = current_time - self.camera_receiver.last_frame_time
                logger.debug(
                    f"VISION frames={self.camera_receiver.frames_received} "
                    f"last_frame_age={age:.1f}s"
                )
            else:
                logger.debug("VISION waiting for frames")
            self._last_vision_status_time = current_time

    # ---------------------------------------------------------------
    # Greeting Detection
    # ---------------------------------------------------------------

    def _is_greeting(self, text: str) -> bool:
        """
        Check if the transcript is a greeting.
        """
        greetings = ["hello", "hi", "hey", "hii", "hola", "good morning", "good afternoon", "good evening"]
        normalized_text = text.strip().lower()
        return normalized_text in greetings

    # ---------------------------------------------------------------
    # Stop Command Detection
    # ---------------------------------------------------------------

    def _is_stop_command(self, text: str) -> bool:
        """
        Check if the transcript is a command to stop TTS.
        """
        stop_commands = ["stop", "cancel", "quiet", "shut up", "pause"]
        normalized_text = text.strip().lower()
        
        for command in stop_commands:
            if command == normalized_text or command in normalized_text:
                return True
        return False

    # ---------------------------------------------------------------
    # Command Mapping
    # ---------------------------------------------------------------

    def _text_to_command(self, text: str) -> dict:
        """
        Convert user text to a robot command dictionary.
        
        Returns:
            dict: Command dictionary, or None if not recognized
        """
        normalized = text.strip().lower()
        
        if any(word in normalized for word in ["move forward", "forward", "go forward"]):
            return {"type": "MOVE", "direction": "FORWARD", "speed": 60, "duration": 2.0}
        
        if any(word in normalized for word in ["move backward", "backward", "go backward", "back up"]):
            return {"type": "MOVE", "direction": "BACKWARD", "speed": 60, "duration": 2.0}
        
        if any(word in normalized for word in ["turn left", "left"]):
            return {"type": "TURN", "direction": "LEFT", "speed": 50, "duration": 1.0}
        
        if any(word in normalized for word in ["turn right", "right"]):
            return {"type": "TURN", "direction": "RIGHT", "speed": 50, "duration": 1.0}
        
        if "stop" in normalized:
            return {"type": "STOP"}
        
        return None

    def _get_command_confirmation(self, command: dict) -> str:
        """
        Get a spoken confirmation for a command.
        
        Returns:
            str: Short confirmation phrase
        """
        cmd_type = command.get("type", "")
        direction = command.get("direction", "")
        
        if cmd_type == "MOVE":
            if direction == "FORWARD":
                return "Okay, moving forward."
            elif direction == "BACKWARD":
                return "Okay, moving backward."
        
        elif cmd_type == "TURN":
            if direction == "LEFT":
                return "Okay, turning left."
            elif direction == "RIGHT":
                return "Okay, turning right."
        
        elif cmd_type == "STOP":
            return "Stopping."
        
        return "Command sent."

    # ---------------------------------------------------------------
    # Transcript Filtering - MINIMAL LOGIC
    # ---------------------------------------------------------------

    def _should_ignore_transcript(self, text: str) -> bool:
        """
        Filter out only truly insignificant transcripts.
        Uses minimal, clear rules to avoid over-filtering.
        """
        t = text.strip().lower()
        if not t:
            logger.debug(f"Ignored transcript: '{text}'")

            return True

        # Stop commands should be handled even when TTS is busy
        if self._is_stop_command(text):
            return False
        
        if self._is_greeting(text):
            return False
        
        allowed_followups = {"more", "continue","again", "repeat", "yes", "no", "ok", "okay"}
        if t in allowed_followups:
            return False
        
        if t.startswith("step "):
            return False
        
        # Ignore only completely empty or near-empty noise
        if len(t) < 2:
            logger.debug(f"Ignored transcript: '{text}'")

            return True

        
        return False

    # ---------------------------------------------------------------
    # Safety Feedback
    # ---------------------------------------------------------------

    def _handle_safety_feedback(self):
        """
        Handle safety feedback from Pi.
        SILENTLY records safety state.
        NO speech here.
        """
        if not self.command_client or not self.command_client.is_connected():
            return

        statuses = self.command_client.poll_status()

        for status in statuses:
            stype = str(status.get("type", "")).upper()

            # ================= IMU DATA =================
            if stype == "IMU":
                self.latest_imu["x"] = status.get("x", 0.0)
                self.latest_imu["y"] = status.get("y", 0.0)
                self.latest_imu["z"] = status.get("z", 0.0)
                self.latest_imu["timestamp"] = status.get("timestamp", 0.0)

                # TEMP DEBUG (remove later)
                '''logger.info(
                    f"IMU x={self.latest_imu['x']:.2f} "
                    f"y={self.latest_imu['y']:.2f} "
                    f"z={self.latest_imu['z']:.2f}"
                )'''

                continue
            # ============================================

            if stype in ["BLOCKED", "SAFETY_STOP"]:
                self._obstacle_blocked = True
                self.context_manager.set_flag(
                    "blocked_reason",
                    {
                        "reason": "obstacle",
                        "sensor": status.get("blocking_sensor"),
                        "distance": status.get("distance_cm"),
                        "time": time.time(),
                    },
                )
                logger.warning("Safety stop: obstacle detected (silent)")

            elif stype == "CLEAR":
                self._obstacle_blocked = False




    # ---------------------------------------------------------------
    # Interruptible TTS - Non-blocking version
    # ---------------------------------------------------------------

    def _split_into_chunks(self, text: str):
        """Split text into small chunks for interruptible TTS."""
        # First split by punctuation and newlines
        split_pattern = r'(?<=[.!?\n,;:])\s*'
        initial_chunks = re.split(split_pattern, text)
        
        # Remove empty chunks and strip whitespace
        initial_chunks = [chunk.strip() for chunk in initial_chunks if chunk.strip()]
        
        # Further split long chunks (max 30 characters)
        final_chunks = []
        for chunk in initial_chunks:
            if len(chunk) <= 70:
                final_chunks.append(chunk)
            else:
                # Break long chunk into 30-character pieces
                words = chunk.split()
                current_chunk = ""
                
                for word in words:
                    if len(current_chunk) + len(word) + 1 <= 70:
                        if current_chunk:
                            current_chunk += " " + word
                        else:
                            current_chunk = word
                    else:
                        if current_chunk:
                            final_chunks.append(current_chunk)
                        current_chunk = word
                
                if current_chunk:
                    final_chunks.append(current_chunk)
        
        return final_chunks

    def _tts_worker(self, text: str):
        """Background thread worker for interruptible TTS."""
        try:
            # Split text into small chunks
            chunks = self._split_into_chunks(text)
            
            for chunk in chunks:
                # Check if stop event is set before each chunk
                if self._tts_stop_event.is_set():
                    logger.info("TTS interrupted by user")
                    break
                    
                # Speak this chunk
                if chunk:
                    pcm_audio = self.tts_client.synthesize(chunk)
                    self.audio_sender.stream_paced(pcm_audio)
                
                # Small sleep between chunks
                time.sleep(0.02)
                
        except Exception as e:
            logger.exception("TTS worker error")
        finally:
            # Reset TTS state
            self._set_tts_busy(False)
            self.state = BrainState.LISTENING
            self._last_spoken_time = time.monotonic()
            self._tts_stop_event.clear()
            logger.info("TTS worker finished")


    def _speak_interruptible(self, text: str):
        """Non-blocking interruptible TTS using background thread."""
        # Stop any ongoing TTS thread
        if self._tts_thread and self._tts_thread.is_alive():
            self._tts_stop_event.set()
            self._tts_thread.join(timeout=1.0)
        
        # Clear stop event for new thread
        self._tts_stop_event.clear()

        # Set TTS busy state
        self._set_tts_busy(True)
        self.state = BrainState.SPEAKING
        
        # Start background thread
        self._tts_thread = threading.Thread(
            target=self._tts_worker,
            args=(text,),
            daemon=True
        )
        self._tts_thread.start()
        
        # Return immediately (non-blocking)
        return

    # ---------------------------------------------------------------
    # Main Loop
    # ---------------------------------------------------------------

    def run(self):
        if not self.running:
            raise RuntimeError("Brain not started")

        try:
            while self.running:
                try:
                    transcript_stream = self.stt_client.stream_transcripts(
                        self.audio_receiver.audio_chunks()
                    )

                    for text in transcript_stream:

                        if not self.running:
                            break
                        # 🚫 Ignore interim transcripts
                        if text.startswith("__INTERIM__"):
                            continue

                        now = time.monotonic()
                        if now - self._final_speech_time < 0.25:
                            continue
                        self._final_speech_time = now

                        self._handle_safety_feedback()

                        if not text:
                            self._handle_safety_feedback()
                            continue

                        # --- keep your existing logic below exactly same ---
                        # stop command, tts busy, scene/vision routing, etc.
                        # ---------------------------------------------------
                        # Check for stop command at any time (even during TTS)
                        if self._is_stop_command(text):
                            self.behavior_manager.stop_behavior()
                            self._tts_stop_event.set()
                            if self.audio_sender:
                                self.audio_sender.stop()

                            if self.command_client.is_connected():
                                self.command_client.send_command({"type": "STOP"})

                            response = "Okay, stopped."
                            logger.info(f"AI: {response}")
                            self._speak_interruptible(response)
                            continue

                        if self.tts_busy and not self._is_stop_command(text):
                            continue

                        normalized_text = text.strip().lower()
                        current_time = time.monotonic()

                        if (normalized_text == self._last_user_text and
                            current_time - self._last_user_text_time < 0.4):
                            continue

                        self._last_user_text = normalized_text
                        self._last_user_text_time = current_time

                        if self._should_ignore_transcript(text):
                            continue
                        
                        if current_time - self._last_spoken_time < 0.3:
                            continue

                        if self.state != BrainState.LISTENING:
                            continue

                        normalized = text.strip().lower()

                        self._handle_user_text(text)
                        self._handle_safety_feedback()
                        self._print_vision_status()

                except Exception as e:
                    logger.exception("STT stream crashed")
                    time.sleep(0.5)
                    continue

        except KeyboardInterrupt:
            logger.info("Interrupted by user")

        finally:
            self.stop()

    # ---------------------------------------------------------------
    # Text Handling
    # ---------------------------------------------------------------

    def _handle_user_text(self, text: str):

        intent = self.intent_classifier.classify(text)

        # --- SAFETY EXPLANATION (ON-DEMAND ONLY) ---
        blocked = self.context_manager.get_flag("blocked_reason")

        if blocked:
            text_l = text.lower()

            explain_triggers = [
                "why",
                "what happened",
                "why did you stop",
                "why are you not moving",
                "what's wrong",
            ]

            retry_triggers = [
                "move forward",
                "go forward",
                "forward",
            ]

            if any(p in text_l for p in explain_triggers + retry_triggers):
                response = "There is an obstacle ahead. I stopped to avoid hitting it."
                logger.info(f"AI: {response}")
                self._speak_interruptible(response)

                # Clear flag so it doesn't repeat forever
                self.context_manager.clear_flag("blocked_reason")
                self.state = BrainState.LISTENING
                return

        logger.info(f"User: {text}")
        self.state = BrainState.PROCESSING

        self.context_manager.add_user_message(text)

        decision = self.planner.decide(
            user_text=text,
            intent=intent,
            context=self.context_manager.get_context(),
        )

        if intent == Intent.SCENE_QUERY:
            response = self._handle_scene_query(text)

            if not response:
                response = self._build_local_scene_summary()
                
            logger.info(f"AI (scene): {response}")
            self._speak_interruptible(response)
            self.context_manager.add_ai_message(response)
            self.state = BrainState.LISTENING
            return

        # ---------------- DIRECT BEHAVIOR TRIGGERS ----------------
        text_l = text.lower()

        assert decision.mode in ("DECISION", "SAFETY")
        logger.debug(f"Planner decision: {decision}")

        # ---------------- BEHAVIOR EXECUTION (from Planner decision) ----------------
        if decision.behavior:
            if decision.behavior.type == "GO_TO_OBJECT":
                if not self.command_client.is_connected():
                    response = "I can't move right now. Motors are not connected."
                    self._speak_interruptible(response)
                    self.state = BrainState.LISTENING
                    return

                started = self.behavior_manager.start_behavior(
                    name="GO_TO_OBJECT",
                    target_fn=go_to_object_loop,
                    scene_state=self.scene_state,
                    command_client=self.command_client,
                    obstacle_flag=lambda: self._obstacle_blocked,
                    target_label=decision.behavior.target,
                )

                response = decision.response.speech or f"Okay, going to the {decision.behavior.target}."
                self._speak_interruptible(response)
                self.context_manager.add_ai_message(response)
                self.state = BrainState.LISTENING
                return

            # (other behavior types can be added here in future)

        # ---------------- COMMAND ----------------
        if intent == Intent.COMMAND:
            self.behavior_manager.stop_behavior()
            command = self._text_to_command(text)
            if command and self.command_client.is_connected():
                self.command_client.send_command(command)
                response = self._get_command_confirmation(command)
            else:
                response = "I don't understand that command."

            self._speak_interruptible(response)
            self.context_manager.add_ai_message(response)
            self.state = BrainState.LISTENING
            return

        # ---------------- NON-COMMAND (UNKNOWN / SAFETY) ----------------
        response = decision.response.speech
        if response:
            self._speak_interruptible(response)
            self.context_manager.add_ai_message(response)

        self.state = BrainState.LISTENING
        return

    # ---------------------------------------------------------------
    # TTS
    # ---------------------------------------------------------------

    def _speak(self, text: str, immediate=False):
        self.state = BrainState.SPEAKING
        
        # Set TTS busy state (except for immediate responses)
        if not immediate:
            self._set_tts_busy(True)
        
        try:
            pcm_audio = self.tts_client.synthesize(text)
            self.audio_sender.stream_paced(pcm_audio)
        finally:
            if not immediate:
                self._set_tts_busy(False)

        self._last_spoken_time = time.monotonic()
        
        self.context_manager.add_ai_message(text)
        self.state = BrainState.LISTENING

    # ---------------------------------------------------------------
    # Shutdown
    # ---------------------------------------------------------------

    def stop(self):
        if not self.running:
            return

        logger.info("Shutting down brain")
        self.running = False

        # Stop TTS thread if running
        self._tts_stop_event.set()
        if self._tts_thread and self._tts_thread.is_alive():
            self._tts_thread.join(timeout=1.0)

        if self.command_client:
            self.command_client.close()

        if self.camera_receiver:
            self.camera_receiver.stop()

        # Wait for YOLO thread to finish
        if self._yolo_thread and self._yolo_thread.is_alive():
            self._yolo_thread.join(timeout=2.0)

        try:
            if self.stt_server:
                self.stt_server.close()
        except Exception:
            pass
        
        try:
            if self.tts_server:
                self.tts_server.close()
        except Exception:
            pass

        logger.info("Shutdown complete")


# -------------------------------------------------------------------
# Entry Point
# -------------------------------------------------------------------

if __name__ == "__main__":
    import time
    import threading
    from scripts.vision_preview import start_preview

    brain = Brain()
    brain.start()

    # Brain logic in background thread
    brain_thread = threading.Thread(
        target=brain.run,
        daemon=True
    )
    brain_thread.start()

    # 🚨 PREVIEW IN MAIN THREAD (macOS REQUIREMENT)
    try:
        start_preview(
            brain.camera_receiver,
            brain,
            brain.preview_stop_event
        )
    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        brain.stop()
