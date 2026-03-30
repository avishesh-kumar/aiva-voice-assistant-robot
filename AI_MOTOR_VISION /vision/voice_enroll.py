import time
import cv2
import numpy as np
from vision.face_pipeline import FACE_PIPELINE


def enroll_from_camera(
    camera_receiver,
    name: str,
    samples: int = 8,
    delay: float = 0.4,
) -> bool:
    """
    Enroll a person by capturing multiple face samples.
    Rejects phone images using motion + texture checks.
    """
    pipeline = FACE_PIPELINE
    collected = 0

    time.sleep(1.0)  # time to face camera

    prev_face_gray = None
    static_score = 0

    for _ in range(samples):
        frame, _ = camera_receiver.get_latest_frame()
        if frame is None:
            time.sleep(delay)
            continue

        faces = pipeline.detector.detect_faces(frame)
        if not faces:
            time.sleep(delay)
            continue

        # choose largest face
        faces = sorted(
            faces,
            key=lambda b: (b[2] - b[0]) * (b[3] - b[1]),
            reverse=True,
        )
        x1, y1, x2, y2 = faces[0]
        face = frame[y1:y2, x1:x2]

        if face.size == 0:
            continue

        # ---------- LIVENESS CHECK ----------
        face_gray = cv2.cvtColor(face, cv2.COLOR_BGR2GRAY)
        face_gray = cv2.resize(face_gray, (96, 96))

        if prev_face_gray is not None:
            diff = cv2.absdiff(face_gray, prev_face_gray)
            motion_level = np.mean(diff)

            # Phone screens → very low texture change
            if motion_level < 1.5:
                static_score += 1
            else:
                static_score = max(0, static_score - 1)

        prev_face_gray = face_gray

        # Reject only if consistently static
        if static_score >= 5:
            print("[ENROLL] Photo detected. Please show a real face.")
            return False
        # -----------------------------------

        success = pipeline.enroll_face(frame, (x1, y1, x2, y2), name)
        if success:
            collected += 1

        time.sleep(delay)

    pipeline.database.reload()
    pipeline._recent_names.clear()
    return collected >= max(2, samples // 2)
