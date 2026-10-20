"""gRPC-сервер ML Engine Stego-Guard.

Реализует контракт stego.v1.StegoService:
  EmbedWatermark — внедряет метку (код содержимого + ID пользователя)
  VerifyDocument — извлекает метку, сверяет код и преамбулу, строит heatmap

Код содержимого считает сам сервер — клиентский content_hash игнорируем.
Сверка пороговая (расстояние Хэмминга по ячейкам): точное равенство
невозможно из-за шума округления, криптографическая привязка появится
в Фазе 2 (реестр в БД).
"""

import logging
import sys
from concurrent import futures
from pathlib import Path

import cv2
import grpc
import numpy as np

sys.path.insert(0, str(Path(__file__).parent / "proto_gen"))

import stego_pb2          # noqa: E402
import stego_pb2_grpc     # noqa: E402

from app.config import (GRPC_PORT, GRPC_MAX_WORKERS, MAX_IMAGE_BYTES,  # noqa: E402
                        BER_THRESHOLD, CODE_CELL_TOLERANCE)
from app.dwt.transform import embed, extract, content_digest, CapacityError  # noqa: E402
from app.dwt.payload import (  # noqa: E402
    pack_payload, unpack_payload, bytes_to_bits, bits_to_bytes,
    PAYLOAD_BITS, HEADER_BITS, PayloadError,
)
from app.verification.ber import bit_error_rate  # noqa: E402
from app.verification.heatmap import build_heatmap  # noqa: E402
from app.verification.authenticity import decide_verdict  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("stego-ml")


def _decode_image(data: bytes) -> np.ndarray:
    """Байты -> изображение OpenCV (uint8). Бросает ValueError, если не картинка."""
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("файл больше 25 МБ")
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError("файл не является изображением")
    if img.dtype != np.uint8:
        img = (img.astype(np.float32) / 257.0).astype(np.uint8)
    if img.ndim == 3 and img.shape[2] == 4:
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    return img


def _code_distance(code_a: bytes, code_b: bytes) -> int:
    """Число различающихся ячеек двух 16-байтных кодов (64 ячейки по 2 бита)."""
    a = np.unpackbits(np.frombuffer(code_a[:16].ljust(16, b"\x00"), np.uint8))
    b = np.unpackbits(np.frombuffer(code_b[:16].ljust(16, b"\x00"), np.uint8))
    return int(np.sum(a[0::2] != b[0::2]) + np.sum(a[1::2] != b[1::2]))


class StegoServicer(stego_pb2_grpc.StegoServiceServicer):
    """Обработчики RPC. Ошибки превращаются в статусы контракта, не вылетают."""

    def EmbedWatermark(self, request, context):
        try:
            image = _decode_image(request.image)
            code = content_digest(image)                    # 16 байт
            digest_field = code.ljust(32, b"\x00")          # поле контракта 32 байта
            bits = bytes_to_bits(pack_payload(digest_field, request.payload.user_id))
            marked = embed(image, bits)

            fmt = (request.output_format or "png").lower()
            if fmt in ("jpeg", "jpg"):
                ok, encoded = cv2.imencode(".jpg", marked, [cv2.IMWRITE_JPEG_QUALITY, 92])
            else:
                ok, encoded = cv2.imencode(".png", marked)
            if not ok:
                raise RuntimeError("не удалось закодировать результат")

            log.info("EmbedWatermark OK: user=%s бит=%d", request.payload.user_id, len(bits))
            return stego_pb2.EmbedResponse(
                watermarked_image=encoded.tobytes(),
                status=stego_pb2.EMBED_OK,
                message=f"метка внедрена ({len(bits)} бит)",
            )
        except CapacityError as e:
            return stego_pb2.EmbedResponse(status=stego_pb2.EMBED_ERROR_PAYLOAD_TOO_LARGE,
                                           message=str(e))
        except ValueError as e:
            return stego_pb2.EmbedResponse(status=stego_pb2.EMBED_ERROR_INVALID_IMAGE,
                                           message=str(e))
        except Exception as e:  # noqa: BLE001
            log.exception("EmbedWatermark failed")
            return stego_pb2.EmbedResponse(status=stego_pb2.EMBED_ERROR_INTERNAL,
                                           message=f"{type(e).__name__}: {e}")

    def VerifyDocument(self, request, context):
        try:
            image = _decode_image(request.image)
            actual_code = content_digest(image)

            bits_a, bits_b, meta = extract(image, PAYLOAD_BITS)
            payload_ber = bit_error_rate(bits_a, bits_b)
            header_ber = bit_error_rate(bits_a[:len(HEADER_BITS)], HEADER_BITS)

            try:
                parsed = unpack_payload(bits_to_bytes(bits_a))
                payload_ok = True
            except PayloadError:
                parsed = None
                payload_ok = False

            if parsed:
                distance = _code_distance(parsed["content_hash"], actual_code)
                hash_match = distance <= CODE_CELL_TOLERANCE
            else:
                distance, hash_match = 999, False
            verdict = decide_verdict(header_ber, payload_ok, hash_match)

            heatmap = (build_heatmap(image, bits_a, bits_b, meta)
                       if verdict == stego_pb2.TAMPERED else b"")

            log.info("VerifyDocument: вердикт=%s BER=%.4f преамбула=%.3f ячеек=%d",
                     stego_pb2.AuthenticityStatus.Name(verdict),
                     payload_ber, header_ber, distance)
            return stego_pb2.VerifyResponse(
                status=verdict,
                ber=payload_ber,
                hash_match=hash_match,
                extracted_hash=parsed["content_hash"] if parsed else b"",
                extracted_user_id=parsed["user_id"] if parsed else "",
                heatmap=heatmap,
                message=f"BER={payload_ber:.4f}, порог={BER_THRESHOLD}",
            )
        except Exception as e:  # noqa: BLE001
            log.exception("VerifyDocument failed")
            return stego_pb2.VerifyResponse(status=stego_pb2.VERIFY_ERROR_INTERNAL,
                                            message=f"{type(e).__name__}: {e}")


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=GRPC_MAX_WORKERS))
    stego_pb2_grpc.add_StegoServiceServicer_to_server(StegoServicer(), server)
    server.add_insecure_port(f"[::]:{GRPC_PORT}")
    server.start()
    log.info("ML-сервис слушает порт %d", GRPC_PORT)
    server.wait_for_termination()


if __name__ == "__main__":
    serve()