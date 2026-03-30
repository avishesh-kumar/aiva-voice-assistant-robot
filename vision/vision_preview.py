import cv2
import time

from vision.face_pipeline import FACE_PIPELINE
from vision.emotion_recognizer import EmotionRecognizer


# 🎨 Box colors (BGR)
COLOR_OBJECT = (0, 255, 0)     # Green
COLOR_FACE = (255, 0, 0)       # Blue
COLOR_TEXT = (0, 0, 255)       # Red


def start_preview(brain):
    """
    Live preview window with:
    - YOLO object boxes
    - Face recognition boxes
    - Emotion labels
    """

    print("[PREVIEW] Starting vision preview window...")

    emotion_model = None
    try:
        emotion_model = EmotionRecognizer()
        print("[PREVIEW] Emotion model loaded")
    except Exception as e:
        print("[PREVIEW] Emotion disabled:", e)

    while True:
        try:
            frame, ts = brain.camera_receiver.get_latest_frame()

            if frame is None:
                time.sleep(0.01)
                continue

            display = frame.copy()

            # ============================================================
            # 🟢 DRAW OBJECT DETECTIONS (YOLO)
            # ============================================================
            objects = getattr(brain, "last_detections", [])

            for obj in objects:
                try:
                    x1, y1, x2, y2 = obj["bbox"]
                    label = obj.get("label", "obj")
                    conf = obj.get("confidence", 0)

                    cv2.rectangle(display, (x1, y1), (x2, y2), COLOR_OBJECT, 2)

                    text = f"{label} {conf:.2f}"
                    cv2.putText(
                        display,
                        text,
                        (x1, max(20, y1 - 5)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        COLOR_OBJECT,
                        2,
                    )
                except Exception:
                    pass

            # ============================================================
            # 🔵 DRAW FACE + EMOTION
            # ============================================================
            faces = FACE_PIPELINE.process_frame(frame)

            for face in faces:
                try:
                    x1, y1, x2, y2 = face["bbox"]
                    name = face.get("name", "Unknown")

                    # Face box
                    cv2.rectangle(display, (x1, y1), (x2, y2), COLOR_FACE, 2)

                    # Name label
                    cv2.putText(
                        display,
                        name,
                        (x1, max(20, y1 - 25)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        COLOR_FACE,
                        2,
                    )

                    # ----------------------------------------------------
                    # ❤️ Emotion
                    # ----------------------------------------------------
                    if emotion_model is not None:
                        face_crop = frame[y1:y2, x1:x2]
                        emotion, conf = emotion_model.predict(face_crop)

                        emo_text = f"{emotion} {conf:.2f}"

                        cv2.putText(
                            display,
                            emo_text,
                            (x1, y2 + 20),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.5,
                            COLOR_TEXT,
                            2,
                        )

                except Exception:
                    pass

            # ============================================================
            # 🖥️ SHOW WINDOW
            # ============================================================
            cv2.imshow("AI Vision Preview", display)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break

        except Exception as e:
            print("[PREVIEW ERROR]", e)
            time.sleep(0.1)

    cv2.destroyAllWindows()
