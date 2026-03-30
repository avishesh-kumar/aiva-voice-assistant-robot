import os
import cv2
import numpy as np
from typing import List, Tuple


class FaceDetector:
    """
    OpenCV DNN-based face detector (SSD).
    Detects multiple faces per frame.
    """

    def __init__(
        self,
        model_path: str = "vision/models/res10_300x300_ssd_iter_140000.caffemodel",
        config_path: str = "vision/models/deploy.prototxt",
        confidence_threshold: float = 0.5,
    ):
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Face model not found: {model_path}")
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Face config not found: {config_path}")

        self.net = cv2.dnn.readNetFromCaffe(config_path, model_path)
        self.confidence_threshold = confidence_threshold

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect_faces(
        self,
        frame_bgr: np.ndarray,
    ) -> List[Tuple[int, int, int, int]]:
        """
        Detect faces in a BGR frame.

        Returns:
            List of bounding boxes (x1, y1, x2, y2)
        """
        h, w = frame_bgr.shape[:2]

        blob = cv2.dnn.blobFromImage(
            frame_bgr,
            scalefactor=1.0,
            size=(300, 300),
            mean=(104.0, 177.0, 123.0),
            swapRB=False,
            crop=False,
        )

        self.net.setInput(blob)
        detections = self.net.forward()

        boxes: List[Tuple[int, int, int, int]] = []

        for i in range(detections.shape[2]):
            confidence = detections[0, 0, i, 2]
            if confidence < self.confidence_threshold:
                continue

            box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
            x1, y1, x2, y2 = box.astype(int)

            # Clamp to image bounds
            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(w, x2)
            y2 = min(h, y2)

            if x2 > x1 and y2 > y1:
                boxes.append((x1, y1, x2, y2))

        return boxes

