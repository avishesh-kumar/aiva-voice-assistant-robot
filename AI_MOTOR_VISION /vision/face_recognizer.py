import os
import cv2
import numpy as np
import onnxruntime as ort
from typing import Tuple, Optional


class FaceRecognizer:
    """
    ArcFace-based face recognizer.

    Responsibilities:
    - Preprocess face crops
    - Run ArcFace ONNX inference
    - Return 512-D embeddings
    """

    def __init__(
        self,
        model_path: str = "vision/models/face/arcface.onnx",
        input_size: Tuple[int, int] = (112, 112),
    ):
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"ArcFace model not found: {model_path}")

        self.model_path = model_path
        self.input_size = input_size

        self.session = ort.InferenceSession(
            self.model_path,
            providers=["CPUExecutionProvider"],
        )

        self.input_name = self.session.get_inputs()[0].name

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_embedding(
        self,
        frame_bgr: np.ndarray,
        bbox: Tuple[int, int, int, int],
    ) -> Optional[np.ndarray]:
        """
        Extract a 512-D face embedding from a frame.

        Args:
            frame_bgr: OpenCV BGR image
            bbox: (x1, y1, x2, y2) face bounding box

        Returns:
            embedding: np.ndarray shape (512,) or None if invalid
        """
        face = self._crop_face(frame_bgr, bbox)
        if face is None:
            return None

        face_input = self._preprocess(face)

        embedding = self._infer(face_input)

        # L2 normalize (standard for ArcFace)
        embedding = embedding / np.linalg.norm(embedding)

        return embedding

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _crop_face(
        self,
        frame: np.ndarray,
        bbox: Tuple[int, int, int, int],
    ) -> Optional[np.ndarray]:
        x1, y1, x2, y2 = bbox
        h, w = frame.shape[:2]

        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(w, x2)
        y2 = min(h, y2)

        if x2 <= x1 or y2 <= y1:
            return None

        return frame[y1:y2, x1:x2]

    def _preprocess(self, face_bgr: np.ndarray) -> np.ndarray:
        """
        Convert face image to ArcFace input tensor.

        Output shape: (1, 112, 112, 3), float32, RGB
        """
        # BGR -> RGB
        face_rgb = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2RGB)

        # Resize
        face_resized = cv2.resize(face_rgb, self.input_size)

        # Normalize to [-1, 1]
        face_norm = (face_resized.astype(np.float32) - 127.5) / 128.0

        # NHWC -> add batch dim
        face_input = np.expand_dims(face_norm, axis=0)

        return face_input

    def _infer(self, face_input: np.ndarray) -> np.ndarray:
        output = self.session.run(
            None,
            {self.input_name: face_input},
        )
        embedding = output[0][0]  # shape (512,)
        return embedding

