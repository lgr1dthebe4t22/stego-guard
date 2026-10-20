"""Расчёт Bit Error Rate — доли несовпадающих битов двух копий метки."""

import numpy as np


def bit_error_rate(bits_a, bits_b) -> float:
    """BER двух копий метки: 0.0 — идеально совпали, 1.0 — полностью различаются."""
    a = np.asarray(bits_a, dtype=np.uint8)
    b = np.asarray(bits_b, dtype=np.uint8)
    if a.size == 0:
        return 0.0
    return float(np.mean(a != b))