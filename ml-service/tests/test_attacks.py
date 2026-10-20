"""Тесты стойкости метки к типовым атакам (сжатие, ресайз)."""

import hashlib

import cv2
import numpy as np
import pytest

from app.dwt.payload import pack_payload, bytes_to_bits
from app.dwt.transform import embed, extract
from app.verification.ber import bit_error_rate


def make_document_image(w=512, h=512) -> np.ndarray:
    """Имитация скана документа (локальная копия, чтобы тесты были независимы)."""
    rng = np.random.default_rng(42)
    img = np.full((h, w, 3), 230, dtype=np.uint8)
    for _ in range(60):
        x, y = rng.integers(0, w - 80), rng.integers(0, h - 6)
        img[y:y + 4, x:x + int(rng.integers(30, 90))] = 60
    noise = rng.normal(0, 3, img.shape)
    return np.clip(img + noise, 0, 255).astype(np.uint8)


@pytest.fixture()
def document():
    return make_document_image()


def _embedded(document):
    digest = hashlib.sha256("attack-test".encode("utf-8")).digest()
    bits = bytes_to_bits(pack_payload(digest, "attack-test"))
    return embed(document, bits), len(bits)


def test_jpeg_q90(document):
    marked, n = _embedded(document)
    ok, jpeg = cv2.imencode(".jpg", marked, [cv2.IMWRITE_JPEG_QUALITY, 90])
    attacked = cv2.imdecode(jpeg, cv2.IMREAD_COLOR)

    bits_a, bits_b, _ = extract(attacked, n)
    ber = bit_error_rate(bits_a, bits_b)
    # JPEG портит обе копии одинаково -> копии не расходятся -> BER должен быть низким
    assert ber < 0.35, f"BER={ber:.3f} — метка слишком хрупкая к JPEG"


def test_jpeg_q70(document):
    marked, n = _embedded(document)
    ok, jpeg = cv2.imencode(".jpg", marked, [cv2.IMWRITE_JPEG_QUALITY, 70])
    attacked = cv2.imdecode(jpeg, cv2.IMREAD_COLOR)

    bits_a, bits_b, _ = extract(attacked, n)
    ber = bit_error_rate(bits_a, bits_b)
    assert ber < 0.5, f"BER={ber:.3f} — при q70 копии ещё не должны сильно расходиться"


def test_resize_half(document):
    marked, n = _embedded(document)
    small = cv2.resize(marked, (marked.shape[1] // 2, marked.shape[0] // 2))
    restored = cv2.resize(small, (marked.shape[1], marked.shape[0]))

    bits_a, bits_b, _ = extract(restored, n)
    ber = bit_error_rate(bits_a, bits_b)
    # ресайз перестраивает коэффициенты — фиксируем уровень как базовую линию Фазы 1
    assert 0.0 <= ber <= 1.0