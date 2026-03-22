"""
scripts/centralized_train.py
=============================
Trains a single centralized model on ALL hospital data combined.
Used as a baseline comparison against the federated learning approach.

This represents the "ideal but privacy-violating" scenario where all
hospitals share their raw data with a central server.

Results saved to: data/centralized_results.json

Usage:
    python scripts/centralized_train.py --data-dir ./data/hospitals --epochs 5

Paper usage:
    Compare federated accuracy vs centralized accuracy.
    The gap shows the "privacy cost" of federated learning.
    A small gap proves FL is viable for medical imaging.
"""

import os
import sys
import json
import time
import argparse
import hashlib
from pathlib import Path
from datetime import datetime

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, ConcatDataset
from torchvision import transforms, models
from torchvision.datasets import ImageFolder
from sklearn.metrics import (
    accuracy_score, precision_score,
    recall_score, f1_score, roc_auc_score
)


# ── MODEL ─────────────────────────────────────────────────────────────────────

class PneumoniaModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.model = models.resnet18(weights=models.ResNet18_Weights.IMAGENET1K_V1)
        self.model.fc = nn.Linear(self.model.fc.in_features, 2)

    def forward(self, x):
        return self.model(x)


# ── EVALUATION ────────────────────────────────────────────────────────────────

def evaluate(model, dataloader, criterion, device):
    model.eval()
    total_loss = 0.0
    y_true, y_pred, y_proba = [], [], []

    with torch.no_grad():
        for images, labels in dataloader:
            images, labels = images.to(device), labels.to(device)
            outputs    = model(images)
            loss       = criterion(outputs, labels)
            total_loss += loss.item() * images.size(0)
            proba      = torch.softmax(outputs, dim=1)
            preds      = torch.argmax(outputs, dim=1)
            y_true.extend(labels.cpu().numpy())
            y_pred.extend(preds.cpu().numpy())
            y_proba.extend(proba[:, 1].cpu().numpy())

    n = len(y_true)
    try:
        auc = roc_auc_score(y_true, y_proba)
    except Exception:
        auc = 0.0

    return {
        'accuracy':  round(accuracy_score(y_true, y_pred), 4),
        'loss':      round(total_loss / n if n > 0 else 0, 4),
        'precision': round(precision_score(y_true, y_pred, zero_division=0), 4),
        'recall':    round(recall_score(y_true, y_pred, zero_division=0), 4),
        'f1_score':  round(f1_score(y_true, y_pred, zero_division=0), 4),
        'auc_roc':   round(auc, 4),
        'num_samples': n
    }


# ── MAIN ──────────────────────────────────────────────────────────────────────

def train_centralized(data_dir: str, epochs: int, batch_size: int = 32,
                      lr: float = 1e-4, num_hospitals: int = 5):

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"\n{'='*60}")
    print(f"  CENTRALIZED TRAINING BASELINE")
    print(f"{'='*60}")
    print(f"  Data dir    : {data_dir}")
    print(f"  Hospitals   : {num_hospitals}")
    print(f"  Epochs      : {epochs}")
    print(f"  Device      : {device}")
    print(f"  NOTE: This violates privacy — raw data combined centrally")
    print(f"  Used ONLY as research comparison baseline")
    print(f"{'='*60}\n")

    transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406],
                             std=[0.229, 0.224, 0.225])
    ])

    # ── Combine all hospital training datasets ────────────────────────────────
    train_datasets = []
    total_samples  = 0

    for h in range(1, num_hospitals + 1):
        h_name    = f'hospital_{h}'
        train_dir = os.path.join(data_dir, h_name, 'train')

        if not os.path.exists(train_dir):
            print(f"  WARNING: {train_dir} not found, skipping {h_name}")
            continue

        ds = ImageFolder(train_dir, transform=transform)
        train_datasets.append(ds)
        total_samples += len(ds)
        print(f"  {h_name}: {len(ds)} training images")

    if not train_datasets:
        print("ERROR: No hospital data found. Run split_dataset.py first.")
        sys.exit(1)

    combined_train = ConcatDataset(train_datasets)

    # Use hospital_1's val and test as shared evaluation sets
    val_dir  = os.path.join(data_dir, 'hospital_1', 'val')
    test_dir = os.path.join(data_dir, 'hospital_1', 'test')

    val_dataset  = ImageFolder(val_dir,  transform=transform)
    test_dataset = ImageFolder(test_dir, transform=transform)

    train_loader = DataLoader(combined_train, batch_size=batch_size,
                              shuffle=True,  num_workers=0)
    val_loader   = DataLoader(val_dataset,   batch_size=batch_size,
                              shuffle=False, num_workers=0)
    test_loader  = DataLoader(test_dataset,  batch_size=batch_size,
                              shuffle=False, num_workers=0)

    print(f"\n  Combined train: {total_samples} images")
    print(f"  Val:  {len(val_dataset)} images")
    print(f"  Test: {len(test_dataset)} images\n")

    # ── Train ────────────────────────────────────────────────────────────────
    model     = PneumoniaModel().to(device)
    optimizer = optim.Adam(model.parameters(), lr=lr)
    criterion = nn.CrossEntropyLoss()

    history      = []
    training_start = time.time()

    print(f"  {'Epoch':<8} {'Train Loss':<14} {'Train Acc':<14} {'Val Loss':<12} {'Val Acc'}")
    print(f"  {'-'*60}")

    for epoch in range(1, epochs + 1):
        model.train()
        epoch_loss = correct = total = 0

        for images, labels in train_loader:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            outputs = model(images)
            loss    = criterion(outputs, labels)
            loss.backward()
            optimizer.step()

            epoch_loss += loss.item() * images.size(0)
            preds       = torch.argmax(outputs, dim=1)
            correct    += (preds == labels).sum().item()
            total      += labels.size(0)

        avg_loss = epoch_loss / total
        acc      = correct / total
        val_m    = evaluate(model, val_loader, criterion, device)

        history.append({
            'epoch':        epoch,
            'train_loss':   round(avg_loss, 4),
            'train_acc':    round(acc, 4),
            'val_loss':     val_m['loss'],
            'val_accuracy': val_m['accuracy']
        })

        print(f"  {epoch:<8} {avg_loss:<14.4f} {acc*100:<14.2f} "
              f"{val_m['loss']:<12.4f} {val_m['accuracy']*100:.2f}%")

    # ── Final test evaluation ────────────────────────────────────────────────
    print(f"\n  Running final test evaluation...")
    test_m = evaluate(model, test_loader, criterion, device)
    training_time = time.time() - training_start

    print(f"\n{'='*60}")
    print(f"  CENTRALIZED RESULTS")
    print(f"{'='*60}")
    print(f"  Accuracy  : {test_m['accuracy']*100:.2f}%")
    print(f"  Precision : {test_m['precision']*100:.2f}%")
    print(f"  Recall    : {test_m['recall']*100:.2f}%")
    print(f"  F1 Score  : {test_m['f1_score']:.4f}")
    print(f"  AUC-ROC   : {test_m['auc_roc']:.4f}")
    print(f"  Loss      : {test_m['loss']:.4f}")
    print(f"  Train Time: {training_time:.1f}s")
    print(f"  Samples   : {total_samples}")
    print(f"{'='*60}\n")

    # ── Save results ─────────────────────────────────────────────────────────
    results = {
        'accuracy':       test_m['accuracy'],
        'precision':      test_m['precision'],
        'recall':         test_m['recall'],
        'f1_score':       test_m['f1_score'],
        'auc_roc':        test_m['auc_roc'],
        'loss':           test_m['loss'],
        'epochs':         epochs,
        'total_samples':  total_samples,
        'num_hospitals':  num_hospitals,
        'training_time_seconds': round(training_time, 1),
        'timestamp':      datetime.now().isoformat(),
        'training_history': history,
        'note': (
            'Centralized baseline — all hospital data combined. '
            'Privacy-violating. Used only for FL comparison.'
        )
    }

    out_path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            'data', 'centralized_results.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"  Results saved to: {out_path}")
    print(f"\n  Compare with FL results:")
    print(f"    FL Accuracy    (check /model-status on website)")
    print(f"    Central Accuracy: {test_m['accuracy']*100:.2f}%")
    print(f"    Gap = privacy cost of federated learning\n")

    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Centralized training baseline for FL comparison'
    )
    parser.add_argument('--data-dir', default='./data/hospitals',
                        help='Path to hospital data folders (default: ./data/hospitals)')
    parser.add_argument('--epochs', type=int, default=5,
                        help='Training epochs (default: 5, match FL epochs)')
    parser.add_argument('--batch-size', type=int, default=32)
    parser.add_argument('--lr', type=float, default=1e-4)
    parser.add_argument('--hospitals', type=int, default=5)
    args = parser.parse_args()

    train_centralized(
        data_dir=args.data_dir,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        num_hospitals=args.hospitals
    )