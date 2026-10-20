"""Сквозной e2e-тест Stego-Guard через HTTP-гейтвей.

Сценарий:
  1. защитить документ (embed)          -> ожидание: 200 + файл
  2. проверить защищённый (verify)      -> ожидание: AUTHENTIC, BER = 0
  3. подделать документ, проверить      -> ожидание: TAMPERED + heatmap
  4. проверить незащищённый документ    -> ожидание: NO_WATERMARK

Предусловие: ML-сервис (50051) и гейтвей (8080) ЗАПУЩЕНЫ.
Запуск: python scripts/e2e_check.py
Код выхода: 0 — всё ок, 1 — есть провалы.
"""

import json
import socket
import sys
import uuid
from pathlib import Path

import cv2
import numpy as np

GATEWAY = "http://localhost:8080"
ML_PORT = 50051
GATEWAY_PORT = 8080

TMP = Path(__file__).resolve().parent.parent / "data" / "samples"
TMP.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------- утилиты

def port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) == 0


def make_document(path: Path, seed: int = 7) -> None:
    """Синтетический скан документа."""
    rng = np.random.default_rng(seed)
    img = np.full((512, 512, 3), 230, np.uint8)
    for _ in range(60):
        x, y = rng.integers(0, 430), rng.integers(0, 506)
        img[y:y + 4, x:x + int(rng.integers(30, 90))] = 60
    img = np.clip(img + rng.normal(0, 3, img.shape), 0, 255).astype(np.uint8)
    cv2.imwrite(str(path), img)


def multipart_request(url: str, file_path: Path, user_id: str = "") -> tuple[int, bytes]:
    """POST multipart/form-data через stdlib (без зависимостей)."""
    import http.client
    import mimetypes

    boundary = uuid.uuid4().hex
    body = bytearray()
    if user_id:
        body += (f"--{boundary}\r\n"
                 f'Content-Disposition: form-data; name="user_id"\r\n\r\n'
                 f"{user_id}\r\n").encode()
    ctype = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    body += (f"--{boundary}\r\n"
             f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'
             f"Content-Type: {ctype}\r\n\r\n").encode()
    body += file_path.read_bytes()
    body += f"\r\n--{boundary}--\r\n".encode()

    conn = http.client.HTTPConnection("localhost", GATEWAY_PORT, timeout=30)
    conn.request("POST", url, bytes(body), {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    })
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp.status, data


# ---------------------------------------------------------------- сценарий

def main() -> int:
    checks = []

    def check(name: str, ok: bool, detail: str = ""):
        checks.append((name, ok))
        print(f"  [{'OK' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

    print("== Stego-Guard e2e проверка ==\n")

    # предусловия
    if not port_open(ML_PORT) or not port_open(GATEWAY_PORT):
        print("ML-сервис или гейтвей не запущены!")
        print("  Терминал 1: cd ml-service && python -m app.server")
        print("  Терминал 2: cd api-gateway && go run ./cmd/gateway")
        return 1
    check("сервисы доступны", True, f"ML:{ML_PORT}, gateway:{GATEWAY_PORT}")

    doc = TMP / "e2e_document.png"
    protected = TMP / "e2e_protected.png"
    forged = TMP / "e2e_forged.png"
    make_document(doc)

    # 1. embed
    status, body = multipart_request("/api/v1/embed", doc, user_id="E2E-TEST")
    ok = status == 200 and len(body) > 1000
    if ok:
        protected.write_bytes(body)
    check("embed: документ защищён", ok, f"HTTP {status}, {len(body)} байт")

    # 2. verify защищённого
    status, body = multipart_request("/api/v1/verify", protected)
    data = json.loads(body) if status == 200 else {}
    check("verify: AUTHENTIC", status == 200 and data.get("status") == "AUTHENTIC"
          and data.get("ber") == 0 and data.get("user_id") == "E2E-TEST",
          f"status={data.get('status')}, BER={data.get('ber')}, user={data.get('user_id')}")

    # 3. подделка -> TAMPERED
    img = cv2.imread(str(protected))
    img[100:250, 100:250] = (0, 0, 200)
    cv2.imwrite(str(forged), img)
    status, body = multipart_request("/api/v1/verify", forged)
    data = json.loads(body) if status == 200 else {}
    check("verify: TAMPERED пойман", status == 200 and data.get("status") == "TAMPERED"
          and data.get("ber", 0) > 0 and bool(data.get("heatmap_base64")),
          f"status={data.get('status')}, BER={round(data.get('ber', 0), 4)}, "
          f"heatmap={'есть' if data.get('heatmap_base64') else 'НЕТ'}")

    # 4. чистый документ -> NO_WATERMARK
    status, body = multipart_request("/api/v1/verify", doc)
    data = json.loads(body) if status == 200 else {}
    check("verify: NO_WATERMARK", status == 200 and data.get("status") == "NO_WATERMARK",
          f"status={data.get('status')}")

    failed = [n for n, ok in checks if not ok]
    print(f"\nИтог: {len(checks) - len(failed)}/{len(checks)} проверок пройдено")
    if failed:
        print("Провалы:", ", ".join(failed))
        return 1
    print("E2E ПРОЙДЕН ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())