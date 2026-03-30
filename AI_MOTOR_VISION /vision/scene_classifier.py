import torch
import torchvision.transforms as T
from torchvision import models
from PIL import Image

class SceneClassifier:
    def __init__(self):
        self.model = models.resnet18(num_classes=365)
        checkpoint = torch.load(
            "models/places365/resnet18_places365.pth.tar",
            map_location="cpu"
        )
        state_dict = {k.replace("module.", ""): v for k, v in checkpoint["state_dict"].items()}
        self.model.load_state_dict(state_dict)
        self.model.eval()

        self.transform = T.Compose([
            T.Resize((224, 224)),
            T.ToTensor(),
            T.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225]
            ),
        ])

        with open("models/places365/categories_places365.txt") as f:
            self.labels = [l.strip().split(" ")[0][3:] for l in f.readlines()]

    def classify(self, frame):
        img = Image.fromarray(frame[:, :, ::-1])
        x = self.transform(img).unsqueeze(0)

        with torch.no_grad():
            logits = self.model(x)
            idx = logits.argmax().item()

        return self.labels[idx]

