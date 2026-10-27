"""gRPC-сервер ML Engine Stego-Guard v2.0.

Реализует контракт stego.v1.StegoService:
  EmbedWatermark — внедряет DWT-метку
  VerifyDocument — извлекает метку + нейросетевой анализ подлинности
"""

import logging
import os
import sys
from concurrent import futures
from pathlib import Path

import cv2
import grpc
import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).parent / "proto_gen"))

import stego_pb2          # noqa: E402
import stego_pb2_grpc     # noqa: E402

from app.config import (GRPC_PORT, GRPC_MAX_WORKERS, MAX_IMAGE_BYTES,  # noqa: E402
                        BER_THRESHOLD, HEADER_BER_THRESHOLD, CODE_CELL_TOLERANCE)
from app.dwt.transform import embed, extract, content_digest, CapacityError  # noqa: E402
from app.dwt.payload import (  # noqa: E402
    pack_payload, unpack_payload, bytes_to_bits, bits_to_bytes,
    PAYLOAD_BITS, HEADER_BITS, PayloadError,
)
from app.verification.ber import bit_error_rate  # noqa: E402
from app.verification.heatmap import build_heatmap  # noqa: E402
from app.verification.authenticity import decide_verdict  # noqa: E402

# Lazy neural verifier
_verifier = None
_verifier_device = None


def _get_verifier():
    """Lazy-load neural DocumentVerifier."""
    global _verifier, _verifier_device
    if _verifier is None:
        try:
            from app.neural.model import DocumentVerifier
            _verifier_device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            _verifier = DocumentVerifier().to(_verifier_device)
            model_path = os.environ.get("VERIFIER_MODEL", "models/verification_best.pth")
            if os.path.exists(model_path):
                ckpt = torch.load(model_path, map_location=_verifier_device)
                _verifier.load_state_dict(ckpt["model"])
                _verifier.eval()
                log.info("Neural verifier loaded from %s", model_path)
            else:
                log.warning("Neural model not found at %s, running without it", model_path)
        except Exception as e:
            log.warning("Neural verifier init failed: %s", e)
            _verifier = "disabled"
    return _verifier if _verifier != "disabled" else None


def _neural_score(image: np.ndarray) -> float:
    """0.0 = original, 1.0 = forged. Returns 0.0 if verifier unavailable."""
    verifier = _get_verifier()
    if verifier is None:
        return 0.0

    # Convert to RGB 512x512
    if len(image.shape) == 2:
        img_rgb = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
    elif image.shape[2] == 4:
        img_rgb = cv2.cvtColor(image, cv2.COLOR_BGRA2RGB)
    elif image.shape[2] == 3:
        img_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    else:
        return 0.0

    img_rgb = cv2.resize(img_rgb, (512, 512))
    tensor = torch.from_numpy(img_rgb.astype(np.float32) / 255.0).permute(2, 0, 1).unsqueeze(0)
    tensor = tensor.to(_verifier_device)

    with torch.no_grad():
        score = torch.sigmoid(verifier(tensor)).item()
    return score


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
    """Обработчики RPC."""

    def EmbedWatermark(self, request, context):
        try:
            image = _decode_image(request.image)

            # защита от повторного внедрения
            bits_a, _, _ = extract(image, PAYLOAD_BITS)
            if bit_error_rate(bits_a[:len(HEADER_BITS)], HEADER_BITS) <= HEADER_BER_THRESHOLD:
                return stego_pb2.EmbedResponse(
                    status=stego_pb2.EMBED_ERROR_INVALID_IMAGE,
                    message="файл уже содержит метку Stego-Guard — перезащита запрещена",
                )

            code = content_digest(image)
            digest_field = code.ljust(32, b"\x00")
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

            # DWT extraction
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

            # Neural check
            neural_score = _neural_score(image)  # 0.0 = original, 1.0 = forged

            # Combined verdict
            dwt_verdict = decide_verdict(header_ber, payload_ok, hash_match)

            if dwt_verdict == stego_pb2.AUTHENTIC:
                # Для защищённых документов доверяем DWT
                verdict = stego_pb2.AUTHENTIC
                message = "Документ подлинный (DWT-метка подтверждена)"
            elif dwt_verdict == stego_pb2.TAMPERED:
                verdict = stego_pb2.TAMPERED
                message = "Подделка подтверждена DWT"
            else:  # NO_WATERMARK
                # Нейросеть помогает только для незащищённых
                if neural_score >= 0.7:
                    verdict = stego_pb2.TAMPERED
                    message = "Метка отсутствует, нейросеть обнаружила подделку"
                else:
                    verdict = stego_pb2.NO_WATERMARK
                    message = "Метка не найдена, документ не защищён"

            heatmap = (build_heatmap(image, bits_a, bits_b, meta)
                       if dwt_verdict == stego_pb2.TAMPERED else b"")

            log.info("VerifyDocument: вердикт=%s BER=%.4f neural=%.3f ячеек=%d",
                     stego_pb2.AuthenticityStatus.Name(verdict),
                     payload_ber, neural_score, distance)

            return stego_pb2.VerifyResponse(
                status=verdict,
                ber=payload_ber,
                hash_match=hash_match,
                extracted_hash=parsed["content_hash"] if parsed else b"",
                extracted_user_id=parsed["user_id"] if parsed else "",
                heatmap=heatmap,
                message=message,
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