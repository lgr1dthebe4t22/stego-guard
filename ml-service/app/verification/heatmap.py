"""Построение тепловой карты зон вмешательства.

Копии A и B метки разнесены по изображению. Если в регион вмешались,
биты этой зоны в одной копии читаются с ошибкой, во второй — нет —
позиция расхождения отмечается на карте. Пиксель субполосы (r, c)
соответствует блоку 2x2 исходного изображения в (2r, 2c).
"""

import cv2
import numpy as np


def build_heatmap(image: np.ndarray, bits_a, bits_b, meta) -> bytes:
    """PNG тепловой карты (красные пятна — зоны вмешательства). Пусто, если ошибок нет."""
    pos_a, lh_shape, hl_shape = meta
    mismatch = np.asarray(bits_a) != np.asarray(bits_b)
    if not mismatch.any():
        return b""

    lh_rows, lh_cols = lh_shape
    lh_size = lh_rows * lh_cols
    h, w = image.shape[:2]
    mask = np.zeros((h, w), dtype=np.float32)

    for i in np.flatnonzero(mismatch):
        pos = int(pos_a[i])
        if pos < lh_size:
            r, c = divmod(pos, lh_cols)
        else:
            r, c = divmod(pos - lh_size, hl_shape[1])
        r2 = min(2 * r, h - 2)
        c2 = min(2 * c, w - 2)
        mask[r2:r2 + 2, c2:c2 + 2] += 1.0

    norm = cv2.normalize(mask, None, 0, 255, cv2.NORM_MINMAX)
    norm = cv2.GaussianBlur(norm, (9, 9), 0)
    heat = cv2.applyColorMap(norm.astype(np.uint8), cv2.COLORMAP_JET)

    bgr = image if image.ndim == 3 else cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    overlay = cv2.addWeighted(heat, 0.55, bgr, 0.45, 0)

    ok, png = cv2.imencode(".png", overlay)
    return png.tobytes() if ok else b""