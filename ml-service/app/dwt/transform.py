"""DWT-пайплайн: внедрение битов метки, извлечение, код содержимого.

Метод внедрения: квантование вейвлет-коэффициентов с шагом DELTA:
  бит 1 -> остаток в [0, DELTA/2), бит 0 -> остаток в [DELTA/2, DELTA).

Устойчивость: каждый бит пишется в группу из REDUNDANCY соседних коэффициентов,
чтение — по среднему остатку группы. Шум JPEG усредняется.

Метка внедряется ДВАЖДЫ. Копии A и B разнесены по всему изображению:
  - локальное вмешательство бьёт по одной копии -> копии расходятся -> BER растёт;
  - JPEG портит обе одинаково -> BER низкий, целостность ловит CRC и сверка кода.

Код содержимого: LL не модифицируется внедрением, но uint8-округления
добавляют шум ±2 — поэтому сильное усреднение (8x8 сетка, 2 бита/ячейка)
и пороговое сравнение, а не sha256: sha отличается при любой 1 ячейке,
а границы округления шумом достижимы всегда.
"""

import cv2
import numpy as np
import pywt

from app.config import WAVELET, DELTA, REDUNDANCY


class CapacityError(Exception):
    """Изображение слишком мало, метка не влезает."""


def _to_y_channel(image):
    """Выделяет канал яркости. Возвращает (Y float32, YCrCb float32 или None)."""
    if image.ndim == 2:
        return image.astype(np.float32), None
    ycrcb = cv2.cvtColor(image[:, :, :3], cv2.COLOR_BGR2YCrCb).astype(np.float32)
    return ycrcb[:, :, 0], ycrcb


def _group_index(n_coeffs: int, n_bits: int):
    """Индексы групп коэффициентов для копий A и B (форма (n_bits, REDUNDANCY))
    и стартовые позиции групп A (для heatmap)."""
    cell = n_coeffs // (2 * n_bits)
    if cell < REDUNDANCY:
        raise CapacityError(
            f"изображение слишком мало: ячейка {cell} коэффициентов, "
            f"нужно минимум {REDUNDANCY} на бит"
        )
    inner = np.arange(REDUNDANCY)
    starts_a = np.arange(n_bits) * cell
    starts_b = starts_a + cell // 2
    return starts_a[:, None] + inner[None, :], starts_b[:, None] + inner[None, :], starts_a


def _write_groups(flat: np.ndarray, idx: np.ndarray, bits) -> None:
    bits = np.asarray(bits, dtype=np.float32)
    chunk = flat[idx]
    base = np.floor(chunk / DELTA) * DELTA
    offset = np.where(bits[:, None] == 1, DELTA / 4.0, 3.0 * DELTA / 4.0)
    flat[idx] = base + offset


def embed(image: np.ndarray, bits) -> np.ndarray:
    """Внедряет биты метки в изображение, возвращает защищённую копию."""
    y, ycrcb = _to_y_channel(image)
    h, w = y.shape
    ll, (lh, hl, hh) = pywt.dwt2(y, WAVELET)

    flat = np.concatenate([lh.ravel(), hl.ravel()])
    n = len(bits)
    if len(flat) < 2 * n * REDUNDANCY:
        raise CapacityError(f"нужно {2 * n * REDUNDANCY} коэффициентов, доступно {len(flat)}")

    idx_a, idx_b, _ = _group_index(len(flat), n)
    _write_groups(flat, idx_a, bits)
    _write_groups(flat, idx_b, bits)

    half = lh.size
    lh = flat[:half].reshape(lh.shape)
    hl = flat[half:].reshape(hl.shape)

    y2 = pywt.idwt2((ll, (lh, hl, hh)), WAVELET)[:h, :w]

    if ycrcb is None:
        return np.clip(y2, 0, 255).astype(np.uint8)
    ycrcb[:, :, 0] = np.clip(y2, 0, 255)
    return cv2.cvtColor(ycrcb.astype(np.uint8), cv2.COLOR_YCrCb2BGR)


def _read_groups(flat: np.ndarray, idx: np.ndarray) -> np.ndarray:
    chunk = flat[idx]
    rest = chunk - np.floor(chunk / DELTA) * DELTA
    return (rest.mean(axis=1) < DELTA / 2).astype(np.uint8)


def extract(image: np.ndarray, n_bits: int):
    """Извлекает копии A и B. Возвращает (bits_a, bits_b, meta);
    meta = (стартовые позиции групп A, форма LH, форма HL) — для heatmap."""
    y, _ = _to_y_channel(image)
    _, (lh, hl, _) = pywt.dwt2(y, WAVELET)
    flat = np.concatenate([lh.ravel(), hl.ravel()])

    idx_a, idx_b, starts_a = _group_index(len(flat), n_bits)
    bits_a = _read_groups(flat, idx_a)
    bits_b = _read_groups(flat, idx_b)
    return bits_a, bits_b, (starts_a, lh.shape, hl.shape)


# ---------------------------------------------------------
# Код содержимого документа
# ---------------------------------------------------------

def _pack_cells(cells: np.ndarray) -> bytes:
    """64 ячейки по 2 бита -> 16 байт (чередование старших и младших бит)."""
    flat = cells.ravel()
    interleaved = np.empty(128, dtype=np.uint8)
    interleaved[0::2] = (flat >> 1) & 1
    interleaved[1::2] = flat & 1
    return np.packbits(interleaved).tobytes()


def content_digest(image: np.ndarray) -> bytes:
    """Код содержимого: 8x8-сетка субполосы LL, 2 бита на ячейку (16 байт).

    LL внедрением не трогается; шум uint8-округлений (±2) после усреднения
    блоками 32x32 на два порядка меньше полушага квантования (32) — код
    детерминированно стабилен. Вмешательство на ~100x100 пикселей меняет
    5+ ячеек и обнаруживается порогом CODE_CELL_TOLERANCE.
    """
    y, _ = _to_y_channel(image)
    ll, _ = pywt.dwt2(y, WAVELET)
    small = cv2.resize(ll, (8, 8), interpolation=cv2.INTER_AREA)
    cells = np.clip(np.round(small / 64.0), 0, 3).astype(np.uint8)
    return _pack_cells(cells)