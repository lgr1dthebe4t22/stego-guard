#!/usr/bin/env python3
import argparse
import os
import sys
import time
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import DataLoader

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))
from neural import DocumentVerifier, VerificationDataset


def accuracy(pred_logits, labels):
    pred = (torch.sigmoid(pred_logits) > 0.5).float()
    return (pred == labels).float().mean().item()


def train_epoch(model, loader, opt, device):
    model.train()
    total_loss = total_acc = 0.0
    criterion = nn.BCEWithLogitsLoss()

    for images, labels in loader:
        images = images.to(device)
        labels = labels.to(device).unsqueeze(1)

        opt.zero_grad()
        logits = model(images)
        loss = criterion(logits, labels)
        loss.backward()
        opt.step()

        total_loss += loss.item()
        total_acc += accuracy(logits, labels)

    return total_loss / len(loader), total_acc / len(loader)


@torch.no_grad()
def validate(model, loader, device):
    model.eval()
    total_loss = total_acc = 0.0
    criterion = nn.BCEWithLogitsLoss()

    for images, labels in loader:
        images = images.to(device)
        labels = labels.to(device).unsqueeze(1)

        logits = model(images)
        loss = criterion(logits, labels)
        total_loss += loss.item()
        total_acc += accuracy(logits, labels)

    return total_loss / len(loader), total_acc / len(loader)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", required=True)
    parser.add_argument("--val", required=True)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--save_dir", default="models")
    args = parser.parse_args()

    device = torch.device(args.device)
    print(f"Device: {device}")

    train_ds = VerificationDataset(args.train)
    val_ds = VerificationDataset(args.val)
    train_loader = DataLoader(
        train_ds, batch_size=args.batch, shuffle=True,
        num_workers=args.workers, pin_memory=False,
    )
    val_loader = DataLoader(
        val_ds, batch_size=args.batch, shuffle=False,
        num_workers=args.workers, pin_memory=False,
    )

    print(f"Train: {len(train_ds)} | Val: {len(val_ds)}")
    print("Начинаем обучение...")

    model = DocumentVerifier().to(device)
    opt = torch.optim.Adam(model.parameters(), lr=args.lr)

    os.makedirs(args.save_dir, exist_ok=True)
    best_acc = 0.0

    for epoch in range(1, args.epochs + 1):
        print(f"\n=== Эпоха {epoch}/{args.epochs} ===")
        t0 = time.time()

        train_loss, train_acc = train_epoch(model, train_loader, opt, args.device)
        val_loss, val_acc = validate(model, val_loader, args.device)
        elapsed = time.time() - t0

        print(f"train_loss={train_loss:.4f} acc={train_acc:.4f}")
        print(f"val_loss={val_loss:.4f} acc={val_acc:.4f}")
        print(f"Время: {elapsed:.1f}s")

        state = {
            "epoch": epoch,
            "model": model.state_dict(),
            "optimizer": opt.state_dict(),
            "best_acc": best_acc,
        }
        torch.save(state, os.path.join(args.save_dir, "verification_last.pth"))

        if val_acc > best_acc:
            best_acc = val_acc
            torch.save(state, os.path.join(args.save_dir, "verification_best.pth"))
            print(f"-> new best acc={best_acc:.4f}")

    print(f"\nГотово! Лучшая точность: {best_acc:.4f}")


if __name__ == "__main__":
    main()