#!/usr/bin/env python3
"""Generate forged document samples from originals."""
import argparse
import cv2
import numpy as np
from pathlib import Path
import random


def apply_forgery(img: np.ndarray) -> np.ndarray:
    h, w = img.shape[:2]

    # JPEG compression artifacts
    quality = random.randint(20, 80)
    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
    _, enc = cv2.imencode(".jpg", img, encode_param)
    img = cv2.imdecode(enc, 1)

    # Gaussian blur
    if random.random() > 0.3:
        k = random.choice([3, 5])
        img = cv2.GaussianBlur(img, (k, k), random.uniform(0.5, 2.0))

    # Resize down-up (loss of detail)
    if random.random() > 0.3:
        scale = random.uniform(0.7, 1.3)
        tmp = cv2.resize(img, (int(w * scale), int(h * scale)))
        img = cv2.resize(tmp, (w, h))

    # Brightness / contrast
    if random.random() > 0.3:
        alpha = random.uniform(0.7, 1.3)
        beta = random.uniform(-30, 30)
        img = cv2.convertScaleAbs(img, alpha=alpha, beta=beta)

    # Noise
    if random.random() > 0.3:
        noise = np.random.normal(0, random.uniform(5, 20), img.shape).astype(np.int16)
        img = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    # Rotation (scan misalignment)
    if random.random() > 0.4:
        angle = random.uniform(-3, 3)
        M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        img = cv2.warpAffine(img, M, (w, h), borderMode=cv2.BORDER_REFLECT)

    return img


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", required=True, help="Source PNG folder (e.g. data/train)")
    parser.add_argument("--out", required=True, help="Output folder (e.g. data/verification)")
    parser.add_argument("--split", type=float, default=0.9, help="Train ratio")
    args = parser.parse_args()

    src = Path(args.src)
    out = Path(args.out)

    files = sorted(src.glob("*.png"))
    if not files:
        raise ValueError(f"No PNG found in {src}")

    split_idx = int(len(files) * args.split)
    splits = [("train", files[:split_idx]), ("val", files[split_idx:])]

    for split_name, file_list in splits:
        (out / split_name / "original").mkdir(parents=True, exist_ok=True)
        (out / split_name / "forged").mkdir(parents=True, exist_ok=True)

        for i, f in enumerate(file_list):
            img = cv2.imread(str(f))
            if img is None:
                continue

            # Original
            cv2.imwrite(str(out / split_name / "original" / f"{i:05d}.png"), img)

            # Forged
            forged = apply_forgery(img)
            cv2.imwrite(str(out / split_name / "forged" / f"{i:05d}.png"), forged)

    print(f"Done. Total files: {len(files)}")


if __name__ == "__main__":
    main()