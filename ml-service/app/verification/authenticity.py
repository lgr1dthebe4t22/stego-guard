"""Логика вердикта подлинности по результатам извлечения метки."""

from app.config import HEADER_BER_THRESHOLD
from app.proto_gen import stego_pb2


def decide_verdict(header_ber: float, payload_ok: bool, hash_match: bool):
    """Возвращает вердикт AuthenticityStatus.

    Дерево решений:
    - преамбула не совпала с эталоном -> NO_WATERMARK
      (метки никогда не было; отличие от «метку уничтожили»)
    - payload разобран (CRC ок) и хэш совпал -> AUTHENTIC
    - иначе                              -> TAMPERED
      (преамбула есть, но payload битый или хэш не сошёлся)
    """
    if header_ber > HEADER_BER_THRESHOLD:
        return stego_pb2.NO_WATERMARK
    if payload_ok and hash_match:
        return stego_pb2.AUTHENTIC
    return stego_pb2.TAMPERED