import cv2
import time
from vision.face_pipeline import FACE_PIPELINE
face_pipeline = FACE_PIPELINE
from vision.emotion_recognizer import EmotionRecognizer
from vision.scene_state import SceneState


def start_preview(camera_receiver, brain, stop_event):
    cv2.namedWindow("Robot Live Camera", cv2.WINDOW_NORMAL)

    # ---------------- FACE RECOGNITION ----------------
    face_pipeline = FACE_PIPELINE
    emotion_recognizer = EmotionRecognizer()
    
    face_frame_count = 0
    FACE_INTERVAL = 2
    last_faces = []
    FACE_COLOR = (255, 0, 255)  # pink

    scene_state = brain.scene_state

    enrolled = False  # 🔒 prevent repeated enrollment

    while not stop_event.is_set():
        frame, ts = camera_receiver.get_latest_frame()

        if frame is None:
            time.sleep(0.01)
            continue

        vis = frame.copy()
        detections = brain.last_detections

        # ---------------- FACE PIPELINE ----------------
        face_frame_count += 1
        has_person = any(d.get("label") == "person" for d in detections)

        if has_person and face_frame_count % FACE_INTERVAL == 0:
            last_faces = face_pipeline.process_frame(frame)

        # ---------------- YOLO OVERLAY ----------------
        for det in detections:
            x1, y1, x2, y2 = det["bbox"]
            cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(
                vis,
                f"{det['label']} {det['confidence']:.2f}",
                (x1, max(y1 - 8, 15)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 0),
                2,
                cv2.LINE_AA,
            )

        # ---------------- FACE + EMOTION OVERLAY ----------------
        for face in last_faces:
            x1, y1, x2, y2 = face["bbox"]
            name = face["name"]
            conf = face["confidence"]

            face_crop = frame[y1:y2, x1:x2]

            emotion, emo_conf = emotion_recognizer.predict(face_crop)

            people = []

            people.append({
                "name": name,
                "confidence": conf,
                "emotion": emotion,
                "emotion_conf": emo_conf,
                "bbox": [x1, y1, x2, y2]
            })

            scene_state.update_people(people)


            # Face box
            cv2.rectangle(vis, (x1, y1), (x2, y2), (255, 0, 0), 2)

            # Name
            cv2.putText(
                vis,
                f"{name} ({conf:.2f})",
                (x1, max(y1 - 12, 15)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 0, 255),
                2,
                cv2.LINE_AA,
            )

            # Emotion (below the face box)
            cv2.putText(
                vis,
                f"{emotion} ({emo_conf:.2f})",
                (x1, y2 + 18),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 255, 255),   # yellow
                2,
                cv2.LINE_AA,
            )


        cv2.imshow("Robot Live Camera", vis)
        key = cv2.waitKey(1) & 0xFF

        if key == ord("q"):
            stop_event.set()
            break

        time.sleep(0.005)

    cv2.destroyAllWindows()
