"""Упаковка/разбор payload метки.

Формат (71 байт = 568 бит):
  [0:2]   магия "SG"          — признак метки Stego-Guard
  [2]     версия схемы        — для будущих миграций формата
  [3:35]  SHA-256 содержимого — 32 байта
  [35:67] ID пользователя     — UTF-8, фиксированное поле 32 байта (дополнено нулями)
  [67:71] CRC32               — контроль целостности payload

Первые 24 бита (магия + версия) — константа, они же ПРЕАМБУЛА:
по их совпадению с эталоном отличаем «метки не было» от «метку уничтожили».
"""

import zlib

MAGIC = b"SG"
SCHEMA_VERSION = 1
USER_ID_MAX_BYTES = 32
PAYLOAD_BYTES = 2 + 1 + 32 + USER_ID_MAX_BYTES + 4   # 71
PAYLOAD_BITS = PAYLOAD_BYTES * 8                     # 568


class PayloadError(ValueError):
    """Payload повреждён или не является меткой Stego-Guard."""


def bytes_to_bits(data: bytes):
    """bytes -> список бит (по 8 бит на байт, старший бит первым)."""
    bits = []
    for byte in data:
        for k in range(7, -1, -1):
            bits.append((byte >> k) & 1)
    return bits


def bits_to_bytes(bits) -> bytes:
    """Список бит -> bytes (обратная операция к bytes_to_bits)."""
    out = bytearray()
    for i in range(0, len(bits) - 7, 8):
        byte = 0
        for k in range(8):
            byte = (byte << 1) | int(bits[i + k])
        out.append(byte)
    return bytes(out)


# Эталон преамблы: магия + версия (24 бита) — константа формата
HEADER_BITS = bytes_to_bits(MAGIC + bytes([SCHEMA_VERSION]))


def pack_payload(content_hash: bytes, user_id: str) -> bytes:
    """Собирает payload из хэша содержимого и ID пользователя."""
    if len(content_hash) != 32:
        raise PayloadError("content_hash должен быть 32 байта (SHA-256)")
    uid = user_id.encode("utf-8")[:USER_ID_MAX_BYTES].ljust(USER_ID_MAX_BYTES, b"\x00")
    body = MAGIC + bytes([SCHEMA_VERSION]) + content_hash + uid
    return body + zlib.crc32(body).to_bytes(4, "big")


def unpack_payload(data: bytes) -> dict:
    """Разбирает payload. Бросает PayloadError, если метка повреждена."""
    if len(data) < PAYLOAD_BYTES:
        raise PayloadError("payload слишком короткий")
    data = data[:PAYLOAD_BYTES]
    body, crc = data[:-4], data[-4:]
    if zlib.crc32(body).to_bytes(4, "big") != crc:
        raise PayloadError("CRC не сошёлся — метка повреждена")
    if body[:2] != MAGIC:
        raise PayloadError("магия не найдена — это не метка Stego-Guard")
    return {
        "schema_version": body[2],
        "content_hash": body[3:35],
        "user_id": body[35:67].rstrip(b"\x00").decode("utf-8", errors="ignore"),
    }