# vision/scene_state.py

import time
import threading
from typing import Dict


class SceneState:
    """
    Shared world model derived from vision.
    Updated by vision thread, read by behaviors.
    """

    def __init__(self, frame_width: int = 640):
        self.frame_width = frame_width

        self.person_visible: bool = False
        self.person_offset_x: float = 0.0
        self.person_area_ratio: float = 0.0

        self.last_update: float = 0.0

        self.people: list = []
        self.objects: list = []
        self.person_boxes: list = []

        self._lock = threading.Lock()

    def update_from_detections(self, detections):
        with self._lock:
            self.person_visible = False
            self.person_offset_x = 0.0
            self.person_area_ratio = 0.0

            persons = [d for d in detections if d.get("label") == "person"]
            self.person_boxes = persons

            if not persons:
                self.last_update = time.time()
                return

            largest = max(persons, key=self._bbox_area)

            x1, y1, x2, y2 = largest["bbox"]
            w = max(1, x2 - x1)
            h = max(1, y2 - y1)
            area = w * h

            cx = (x1 + x2) / 2.0
            frame_cx = self.frame_width / 2.0

            self.person_visible = True
            self.person_offset_x = (cx - frame_cx) / frame_cx
            self.person_area_ratio = area / (self.frame_width * self.frame_width)
            self.last_update = time.time()

    def update_objects(self, objects: list):
        with self._lock:
            self.objects = objects
            self.last_update = time.time()

    def update_people(self, people: list):
        with self._lock:
            self.people = people
            self.last_update = time.time()

    def is_stale(self, max_age: float = 0.4) -> bool:
        return (time.time() - self.last_update) > max_age

    @staticmethod
    def _bbox_area(det: Dict) -> int:
        x1, y1, x2, y2 = det["bbox"]
        return max(0, x2 - x1) * max(0, y2 - y1)
