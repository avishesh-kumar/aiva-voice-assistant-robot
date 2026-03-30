import cv2
import numpy as np
try:
    from tensorflow.keras.models import load_model
    TF_AVAILABLE = True
except Exception:
    TF_AVAILABLE = False

from pathlib import Path


class EmotionRecognizer:
    """
    Real-time facial emotion recognizer using Mini-Xception (FER2013).
    Designed for CPU inference.
    """

    def __init__(self):
        if not TF_AVAILABLE:
            raise RuntimeError("TensorFlow not available — emotion disabled")

        model_path = Path(__file__).parent / "models" / "emotion_mini_xception.h5"

        self.model = load_model(model_path, compile=False)
        self.model.compile()

        print("[EMOTION] Model input shape:", self.model.input_shape)

        self.emotions = [
            "angry",
            "disgust",
            "fear",
            "happy",
            "sad",
            "surprise",
            "neutral"
        ]


    def predict(self, face_bgr):
        if face_bgr is None or face_bgr.size == 0:
            return "neutral", 0.0

        # Convert to grayscale
        gray = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY)

        # Resize to model input size
        gray = cv2.resize(gray, (64, 64))

        # Normalize
        gray = gray.astype("float32") / 255.0

        # Add batch & channel dimensions
        gray = np.expand_dims(gray, axis=0)
        gray = np.expand_dims(gray, axis=-1)

        preds = self.model.predict(gray, verbose=0)[0]

        idx = int(np.argmax(preds))
        confidence = float(preds[idx])

        return self.emotions[idx], confidence

