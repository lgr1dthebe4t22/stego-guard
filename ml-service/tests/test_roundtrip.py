"""Сквозные тесты DWT-пайплайна: внедрение -> извлечение -> вердикт."""

import hashlib

import numpy as np
import pytest

from app.config import CODE_CELL_TOLERANCE
from app.dwt.payload import (pack_payload, unpack_payload, bytes_to_bits,
                             bits_to_bytes, HEADER_BITS, PayloadError)
from app.dwt.transform import embed, extract, content_digest
from app.verification.ber import bit_error_rate
from app.verification.authenticity import decide_verdict
from app.proto_gen import stego_pb2


def make_document_image(w=512, h=512) -> np.ndarray:
    """Имитация скана документа: светлый фон, текстовые блоки (тёмные прямоугольники)."""
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


def _code_distance(code_a: bytes, code_b: bytes) -> int:
    """Как в server.py: число различающихся ячеек двух кодов."""
    a = np.unpackbits(np.frombuffer(code_a[:16].ljust(16, b"\x00"), np.uint8))
    b = np.unpackbits(np.frombuffer(code_b[:16].ljust(16, b"\x00"), np.uint8))
    return int(np.sum(a[0::2] != b[0::2]) + np.sum(a[1::2] != b[1::2]))


def _verify_pipeline(image, n_bits=568):
    """Повторяет логику server.py: извлекает метку и выносит вердикт."""
    bits_a, bits_b, _ = extract(image, n_bits)
    payload_ber = bit_error_rate(bits_a, bits_b)
    header_ber = bit_error_rate(bits_a[:len(HEADER_BITS)], HEADER_BITS)
    try:
        parsed = unpack_payload(bits_to_bytes(bits_a))
        payload_ok = True
    except PayloadError:
        parsed = None
        payload_ok = False
    if parsed:
        distance = _code_distance(parsed["content_hash"], content_digest(image))
        hash_match = distance <= CODE_CELL_TOLERANCE
    else:
        hash_match = False
    return decide_verdict(header_ber, payload_ok, hash_match), payload_ber


def test_payload_pack_unpack_roundtrip():
    digest = hashlib.sha256("документ".encode("utf-8")).digest()
    payload = pack_payload(digest, "UIK-42")
    parsed = unpack_payload(payload)
    assert parsed["content_hash"] == digest
    assert parsed["user_id"] == "UIK-42"
    assert parsed["schema_version"] == 1


def test_payload_rejects_garbage():
    with pytest.raises(PayloadError):
        unpack_payload(b"\x00" * 71)


def test_embed_extract_lossless(document):
    digest = hashlib.sha256("протокол".encode("utf-8")).digest()
    bits = bytes_to_bits(pack_payload(digest, "UIK-777"))
    marked = embed(document, bits)

    assert marked.shape == document.shape
    bits_a, bits_b, _ = extract(marked, len(bits))
    assert bit_error_rate(bits_a, bits_b) == 0.0

    parsed = unpack_payload(bits_to_bytes(bits_a))
    assert parsed["content_hash"] == digest
    assert parsed["user_id"] == "UIK-777"


def test_content_digest_stable_after_embed(document):
    """Код содержимого детерминированно стабилен после внедрения."""
    before = content_digest(document)
    for bits_seed in ([0] * 568, [1] * 568):
        marked = embed(document, bits_seed)
        assert content_digest(marked) == before


def test_code_distance_catches_tamper(document):
    """Вмешательство 150x150 меняет больше ячеек, чем допуск."""
    code_before = content_digest(document)
    tampered = document.copy()
    tampered[100:250, 100:250] = (0, 0, 200)
    distance = _code_distance(code_before, content_digest(tampered))
    assert distance > CODE_CELL_TOLERANCE


def test_verdict_authentic(document):
    digest_field = content_digest(document).ljust(32, b"\x00")
    marked = embed(document, bytes_to_bits(pack_payload(digest_field, "auditor")))
    verdict, ber_val = _verify_pipeline(marked)
    assert ber_val == 0.0
    assert verdict == stego_pb2.AUTHENTIC


def test_verdict_tampered(document):
    digest_field = content_digest(document).ljust(32, b"\x00")
    marked = embed(document, bytes_to_bits(pack_payload(digest_field, "auditor")))
    tampered = marked.copy()
    tampered[100:250, 100:250] = (0, 0, 200)

    verdict, ber_val = _verify_pipeline(tampered)
    assert ber_val > 0.0
    assert verdict == stego_pb2.TAMPERED


def test_verdict_no_watermark(document):
    verdict, _ = _verify_pipeline(document)
    assert verdict == stego_pb2.NO_WATERMARK