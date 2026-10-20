"""Симулятор атак на защищённый документ.

Нужен для: (1) обучения Encoder-Decoder — атаки применяются на лету,
что заставляет модель внедрять метку, переживающую реальный мир;
(2) оценки стойкости — evaluate.py гоняет эти атаки и меряет BER.

Каждая функция: изображение numpy -> атакованное изображение numpy.
"""

import cv2
import numpy as np


def jpeg_compress(image: np.ndarray, quality: int = 85) -> np.ndarray:
    """Пережатие JPEG заданного качества (имитация мессенджеров/соцсетей)."""
    ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        return image
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def resize_scale(image: np.ndarray, scale: float = 0.5) -> np.ndarray:
    """Уменьшение с последующим возвратом к исходному размеру."""
    h, w = image.shape[:2]
    small = cv2.resize(image, (max(1, int(w * scale)), max(1, int(h * scale))),
                       interpolation=cv2.INTER_AREA)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)


def crop_fraction(image: np.ndarray, frac: float = 0.1) -> np.ndarray:
    """Обрезка краёв (доля от размера) с возвратом к исходному размеру."""
    h, w = image.shape[:2]
    dy, dx = int(h * frac), int(w * frac)
    cropped = image[dy:h - dy, dx:w - dx]
    return cv2.resize(cropped, (w, h), interpolation=cv2.INTER_LINEAR)


def rotate_angle(image: np.ndarray, angle: float = 2.0) -> np.ndarray:
    """Поворот на небольшой угол (перефотографирование)."""
    h, w = image.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(image, m, (w, h), borderMode=cv2.BORDER_REPLICATE)


def gaussian_noise(image: np.ndarray, sigma: float = 3.0) -> np.ndarray:
    """Аддитивный шум (плохой сканер)."""
    noise = np.random.default_rng().normal(0, sigma, image.shape)
    return np.clip(image.astype(np.float32) + noise, 0, 255).astype(np.uint8)


# ------------------------------------------------------------- композиты

def attack_messenger(image: np.ndarray) -> np.ndarray:
    """Сценарий «пересылка через мессенджер»: JPEG ~q75 + лёгкий ресайз."""
    return resize_scale(jpeg_compress(image, quality=75), scale=0.85)


def attack_social(image: np.ndarray) -> np.ndarray:
    """Сценарий «публикация в соцсети»: агрессивный JPEG ~q60."""
    return jpeg_compress(image, quality=60)


ATTACKS = {
    "jpeg_q90": lambda img: jpeg_compress(img, 90),
    "jpeg_q75": lambda img: jpeg_compress(img, 75),
    "jpeg_q60": lambda img: jpeg_compress(img, 60),
    "resize_half": lambda img: resize_scale(img, 0.5),
    "crop_10": lambda img: crop_fraction(img, 0.10),
    "rotate_2deg": rotate_angle,
    "noise_sigma3": gaussian_noise,
    "messenger": attack_messenger,
    "social": attack_social,
}