"""Генератор синтетических документов для обучения Encoder-Decoder.

Имитирует сканы избирательных протоколов: текстовые строки, таблицы,
печати/штампы, шум сканера, лёгкий наклон, разное разрешение.

Использование:
    python scripts/generate_dataset.py --count 2000 --val 200
На выходе: data/train/doc_00000.png ... и data/val/doc_00000.png
"""

import argparse
from pathlib import Path

import cv2
import numpy as np

# палитра «канцелярского» документа
PAPER_COLORS = [(232, 232, 232), (240, 240, 240), (248, 248, 248), (225, 230, 225)]
INK_COLORS = [(40, 40, 40), (60, 60, 60), (30, 30, 80), (80, 30, 30)]
STAMP_COLORS = [(180, 60, 60), (60, 100, 200), (60, 140, 60), (160, 100, 40)]


def add_text_block(img, rng, x, y, w, n_lines):
    """Блок «текста»: строки тёмных прямоугольников разной длины."""
    ink = INK_COLORS[int(rng.integers(0, len(INK_COLORS)))]
    line_h = int(rng.integers(4, 7))
    for i in range(n_lines):
        lw = int(w * rng.uniform(0.5, 1.0))
        yy = y + i * (line_h + int(rng.integers(3, 7)))
        img[yy:yy + line_h, x:x + lw] = ink
    return y + n_lines * (line_h + 8)


def add_table(img, rng, x, y, w, rows, cols):
    """Таблица: сетка + зачёркнутые ячейки (как в протоколах)."""
    ink = (50, 50, 50)
    row_h = int(rng.integers(14, 22))
    for r in range(rows + 1):
        yy = y + r * row_h
        cv2.line(img, (x, yy), (x + w, yy), ink, 1)
    for c in range(cols + 1):
        xx = x + int(w * c / cols)
        cv2.line(img, (y and x, y), (xx, y + rows * row_h), ink, 1)
    # содержимое ячеек — короткие штрихи
    for r in range(rows):
        for c in range(cols):
            if rng.uniform() < 0.7:
                cx = x + int(w * c / cols) + 3
                cy = y + r * row_h + int(row_h * 0.4)
                img[cy:cy + 2, cx:cx + int(rng.integers(8, int(w / cols) - 8))] = ink
    return y + rows * row_h + 10


def add_stamp(img, rng):
    """Печать/штамп: круг или прямоугольник полупрозрачным цветом."""
    color = STAMP_COLORS[int(rng.integers(0, len(STAMP_COLORS)))]
    h, w = img.shape[:2]
    cx, cy = int(rng.integers(w // 3, w)), int(rng.integers(h // 2, h))
    if rng.uniform() < 0.5:
        r = int(rng.integers(30, 70))
        cv2.circle(img, (cx, cy), r, color, 2)
        cv2.circle(img, (cx, cy), int(r * 0.7), color, 1)
    else:
        ww, hh = int(rng.integers(60, 120)), int(rng.integers(30, 60))
        cv2.rectangle(img, (cx - ww, cy - hh), (cx + ww, cy + hh), color, 2)


def make_document(rng, size=512):
    paper = PAPER_COLORS[int(rng.integers(0, len(PAPER_COLORS)))]
    img = np.full((size, size, 3), paper, np.uint8)

    margin = int(rng.integers(30, 70))
    y = margin
    # заголовок
    y = add_text_block(img, rng, margin, y, size - 2 * margin,
                       int(rng.integers(1, 3))) + 6
    # тело: чередование текста и таблиц
    while y < size - margin - 40:
        if rng.uniform() < 0.55:
            y = add_text_block(img, rng, margin, y, size - 2 * margin,
                               int(rng.integers(2, 6))) + 6
        else:
            y = add_table(img, rng, margin, y, size - 2 * margin,
                          int(rng.integers(2, 5)), int(rng.integers(2, 5)))
    # 1-2 печати
    for _ in range(int(rng.integers(1, 3))):
        add_stamp(img, rng)
    # шум сканера
    img = np.clip(img.astype(np.float32) + rng.normal(0, rng.uniform(1, 5), img.shape),
                  0, 255).astype(np.uint8)
    # лёгкий наклон
    angle = rng.uniform(-1.2, 1.2)
    m = cv2.getRotationMatrix2D((size / 2, size / 2), angle, 1.0)
    img = cv2.warpAffine(img, m, (size, size), borderValue=paper)
    return img


def generate(count: int, out_dir: Path, seed: int):
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    for i in range(count):
        img = make_document(rng)
        cv2.imwrite(str(out_dir / f"doc_{i:05d}.png"), img)
        if (i + 1) % 500 == 0:
            print(f"  {out_dir.name}: {i + 1}/{count}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=2000, help="документов в train")
    ap.add_argument("--val", type=int, default=200, help="документов в val")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    root = Path(__file__).resolve().parent.parent / "data"
    print(f"Генерация: train={args.count}, val={args.val}")
    generate(args.count, root / "train", args.seed)
    generate(args.val, root / "val", args.seed + 1)
    print("Готово →", root)


if __name__ == "__main__":
    main()