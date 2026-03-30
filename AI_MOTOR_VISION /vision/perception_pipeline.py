import numpy as np
from vision.depth_estimator import DepthEstimator


class PerceptionPipeline:
    def __init__(self, yolo_detector, scene_state):
        self.yolo = yolo_detector
        self.scene_state = scene_state
        self.depth = DepthEstimator()

    def process(self, frame):
        detections = self.yolo.detect(frame)
        depth_map = self.depth.estimate(frame)

        h, w = depth_map.shape
        frame_cx = w / 2.0

        enriched_objects = []

        for det in detections:
            x1, y1, x2, y2 = det["bbox"]

            cx = (x1 + x2) / 2.0
            area = (x2 - x1) * (y2 - y1)

            offset_x = (cx - frame_cx) / frame_cx
            area_ratio = area / (w * h)

            roi_depth = depth_map[y1:y2, x1:x2]
            mean_depth = float(np.mean(roi_depth)) if roi_depth.size > 0 else 1.0

            enriched_objects.append({
                "label": det["label"],
                "confidence": det["confidence"],
                "bbox": det["bbox"],
                "offset_x": offset_x,
                "area_ratio": area_ratio,
                "depth": mean_depth,
            })

        self.scene_state.update_objects(enriched_objects)
        self.scene_state.update_from_detections(enriched_objects)

        return depth_map
    @staticmethod
    def is_forward_blocked(depth_map, threshold=0.2):
        h, w = depth_map.shape
        roi = depth_map[int(h*0.6):h, int(w*0.3):int(w*0.7)]
        return roi.mean() < threshold


