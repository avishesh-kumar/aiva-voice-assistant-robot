import torch
import cv2
import numpy as np


class DepthEstimator:
    def __init__(self):
        self.device = torch.device(
            "mps" if torch.backends.mps.is_available() else "cpu"
        )

        self.model_type = "DPT_Hybrid"
        self.model = torch.hub.load("intel-isl/MiDaS", self.model_type)
        self.model.to(self.device)
        self.model.eval()

        self.transform = torch.hub.load("intel-isl/MiDaS", "transforms").dpt_transform

    def estimate(self, frame_bgr: np.ndarray):
        img = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

        input_batch = self.transform(img).to(self.device)

        with torch.no_grad():
            prediction = self.model(input_batch)
            prediction = torch.nn.functional.interpolate(
                prediction.unsqueeze(1),
                size=img.shape[:2],
                mode="bicubic",
                align_corners=False,
            ).squeeze()

        depth_map = prediction.cpu().numpy()

        # Normalize depth for easier interpretation
        depth_min = depth_map.min()
        depth_max = depth_map.max()
        depth_map = (depth_map - depth_min) / (depth_max - depth_min + 1e-8)

        return depth_map

