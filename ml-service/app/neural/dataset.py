from pathlib import Path
import cv2
import numpy as np
import torch
from torch.utils.data import Dataset


class VerificationDataset(Dataset):
    def __init__(self, root_dir: str, image_size: int = 512):
        self.root_dir = Path(root_dir)
        self.image_size = image_size
        self.classes = ["original", "forged"]
        self.paths = []
        self.labels = []

        for label_idx, cls in enumerate(self.classes):
            cls_dir = self.root_dir / cls
            if cls_dir.exists():
                for p in sorted(cls_dir.glob("*.png")):
                    self.paths.append(p)
                    self.labels.append(label_idx)

    def __len__(self) -> int:
        return len(self.paths)

    def __getitem__(self, idx: int):
        img = cv2.imread(str(self.paths[idx]))
        if img is None:
            raise RuntimeError(f"Cannot read: {self.paths[idx]}")
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = cv2.resize(img, (self.image_size, self.image_size))
        img = img.astype(np.float32) / 255.0
        image = torch.from_numpy(img).permute(2, 0, 1)
        label = torch.tensor(self.labels[idx], dtype=torch.float32)
        return image, label