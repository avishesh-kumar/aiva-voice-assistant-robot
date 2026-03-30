from typing import List, Dict
import numpy as np
from collections import deque

from vision.face_detector import FaceDetector
from vision.face_recognizer import FaceRecognizer
from vision.face_database import FaceDatabase


class FacePipeline:
    """
    End-to-end face recognition pipeline:
    detector → recognizer → database
    """

    def __init__(
        self,
        detection_confidence: float = 0.6,
        recognition_threshold: float = 0.48,
    ):

        self._recent_names = deque(maxlen=5)
        self.detector = FaceDetector(confidence_threshold=detection_confidence)
        self.recognizer = FaceRecognizer()
        self.database = FaceDatabase(similarity_threshold=recognition_threshold)


    def load_known_faces_from_photos(self, base_dir: str):
        self.database.load_from_photo_folders(
            base_dir=base_dir,
            detector=self.detector,
            recognizer=self.recognizer,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_frame(self, frame_bgr: np.ndarray) -> List[Dict]:
        """
        Process a frame and recognize faces.

        Returns:
            List of dicts:
            {
              "name": str,
              "confidence": float,
              "bbox": (x1, y1, x2, y2)
            }
        """
        results = []

        boxes = self.detector.detect_faces(frame_bgr)

        for bbox in boxes:
            embedding = self.recognizer.extract_embedding(frame_bgr, bbox)
            if embedding is None:
                continue

            name, confidence = self.database.match(embedding)

            if name != "Unknown":
                self.database.update_seen(name)

            if name != "Unknown":
                self._recent_names.append(name)
                if self._recent_names.count(name) < 2:
                    name = "Unknown"
            else:
                # do NOT hard reset on one bad frame
                if self._recent_names:
                    self._recent_names.popleft()



            results.append(
                {
                    "name": name,
                    "confidence": float(confidence),
                    "bbox": bbox,
                }
            )

        return results

    def enroll_face(
        self,
        frame_bgr: np.ndarray,
        bbox: tuple,
        name: str,
    ):
        """
        Enroll a new face into the database.
        """
        embedding = self.recognizer.extract_embedding(frame_bgr, bbox)
        if embedding is None:
            return False

        self.database.add_face(name, embedding)
        return True

# ============================================================
# 🔒 SHARED SINGLETON FACE PIPELINE (GLOBAL INSTANCE)
# ============================================================

FACE_PIPELINE = FacePipeline(
    detection_confidence=0.6,
    recognition_threshold=0.48,
)
