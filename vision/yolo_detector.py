# vision/yolo_detector.py
import time
from typing import List, Dict, Optional, Tuple
import numpy as np

# Try to import ultralytics, but don't crash if not installed
try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False

class YOLODetector:
    def __init__(self, model_path: str = "vision/models/yolov8n.pt", conf: float = 0.35, iou: float = 0.45):
        """
        Initialize YOLO detector.
        
        Args:
            model_path: Path to YOLO model file
            conf: Confidence threshold
            iou: IoU threshold for NMS
        """
        self.conf = conf
        self.iou = iou
        self.model = None
        self.model_loaded = False
        self.latest_detections = []
        
        if not YOLO_AVAILABLE:
            raise RuntimeError("ultralytics not installed — YOLO disabled")
        
        try:
            self.model = YOLO(model_path)
            self.model_loaded = True
            print(f"[YOLO] Model loaded from {model_path}")
        except Exception as e:
            print(f"[YOLO] Failed to load model: {e}")
    
    def detect(self, frame: np.ndarray) -> List[Dict]:
        """
        Detect objects in a frame.
        
        Args:
            frame: OpenCV BGR frame (numpy array)
            
        Returns:
            List of detection dictionaries, each with keys:
            - "label": class name (str)
            - "confidence": confidence score (float)
            - "bbox": [x1, y1, x2, y2] (list of ints)
        """
        if not self.model_loaded or frame is None:
            return []
        
        try:
            # Run inference
            results = self.model(frame, conf=self.conf, iou=self.iou, verbose=False)
            
            detections = []
            if results and len(results) > 0:
                boxes = results[0].boxes
                
                if boxes is not None:
                    for box in boxes:
                        # Extract bounding box coordinates (x1, y1, x2, y2)
                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
                        
                        # Get class label and confidence
                        class_id = int(box.cls[0].cpu().numpy())
                        label = results[0].names[class_id]
                        confidence = float(box.conf[0].cpu().numpy())
                        
                        detections.append({
                            "label": label,
                            "confidence": confidence,
                            "bbox": [int(x1), int(y1), int(x2), int(y2)]
                        })
            
            return detections
            
        except Exception as e:
            print(f"[YOLO] Detection error: {e}")
            return []
    
    def summarize(self, detections: List[Dict]) -> Dict[str, int]:
        """
        Summarize detections into counts per label.
        
        Args:
            detections: List of detection dictionaries
            
        Returns:
            Dictionary with label counts, e.g., {"person": 2, "bottle": 1}
        """
        summary = {}
        for detection in detections:
            label = detection["label"]
            summary[label] = summary.get(label, 0) + 1
        return summary
