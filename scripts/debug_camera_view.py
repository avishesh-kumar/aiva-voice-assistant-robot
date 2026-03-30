import sys
from pathlib import Path

# Add project root to Python path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import cv2
import time
import numpy as np
from vision.camera_receiver import CameraReceiver


def main():
    receiver = CameraReceiver(host="0.0.0.0", port=8891)
    receiver.start()

    # ✅ macOS GUI initialization (CRITICAL)
    cv2.namedWindow("Robot Live Camera (Debug)", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Robot Live Camera (Debug)", 960, 540)

    print("[DEBUG] Camera preview started. Press Q to quit.")

    try:
        while True:
            frame, ts = receiver.get_latest_frame()

            if isinstance(frame, np.ndarray) and frame.ndim == 3 and frame.size > 0:
                # ✅ Ensure display-safe format for macOS
                frame_disp = frame

                if frame_disp.dtype != np.uint8:
                    frame_disp = np.clip(frame_disp, 0, 255).astype(np.uint8)

                frame_disp = np.ascontiguousarray(frame_disp)

                # ✅ Force BGR → RGB correction if needed
                frame_disp = cv2.cvtColor(frame_disp, cv2.COLOR_BGR2RGB)

                cv2.imshow("Robot Live Camera (Debug)", frame_disp)


            # ✅ REQUIRED on macOS
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

            time.sleep(0.005)

    finally:
        receiver.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
