"""
scripts/split_dataset_noniid.py
================================
Splits the chest_xray dataset into 5 hospital folders with NON-IID distribution.

Each hospital gets a different class imbalance — simulating real-world
hospital populations where different hospitals see different patient types.

Distribution:
    hospital_1: 80% PNEUMONIA, 20% NORMAL  (heavy pneumonia cases)
    hospital_2: 65% PNEUMONIA, 35% NORMAL
    hospital_3: 50% PNEUMONIA, 50% NORMAL  (balanced)
    hospital_4: 35% PNEUMONIA, 65% NORMAL
    hospital_5: 20% PNEUMONIA, 80% NORMAL  (heavy normal cases)

Usage:
    python scripts/split_dataset_noniid.py --source ./data/chest_xray --dest ./data/hospitals_noniid

Why this matters for research:
    - Real hospitals have different patient demographics
    - Non-IID data is the hardest case for federated learning
    - Shows FedAvg can still converge despite data heterogeneity
    - Standard evaluation benchmark in FL literature
"""

import os
import shutil
import random
import argparse
from pathlib import Path


HOSPITALS = 5
CLASSES   = ['NORMAL', 'PNEUMONIA']
SPLITS    = ['train', 'val', 'test']

# Non-IID distribution: (pneumonia_ratio, normal_ratio) per hospital
# hospital_1 sees mostly pneumonia, hospital_5 sees mostly normal
NONIID_RATIOS = {
    'hospital_1': {'PNEUMONIA': 0.80, 'NORMAL': 0.20},
    'hospital_2': {'PNEUMONIA': 0.65, 'NORMAL': 0.35},
    'hospital_3': {'PNEUMONIA': 0.50, 'NORMAL': 0.50},
    'hospital_4': {'PNEUMONIA': 0.35, 'NORMAL': 0.65},
    'hospital_5': {'PNEUMONIA': 0.20, 'NORMAL': 0.80},
}


def split_noniid(source_dir: str, dest_dir: str, seed: int = 42):
    source = Path(source_dir)
    dest   = Path(dest_dir)

    train_dir = source / 'train'
    val_dir   = source / 'val'
    test_dir  = source / 'test'

    for d in [train_dir, val_dir, test_dir]:
        if not d.exists():
            raise FileNotFoundError(f"Missing: {d}")

    # Create destination folders
    for h in range(1, HOSPITALS + 1):
        for split in SPLITS:
            for cls in CLASSES:
                (dest / f'hospital_{h}' / split / cls).mkdir(parents=True, exist_ok=True)

    random.seed(seed)

    # ── Split TRAIN with non-IID ratios ──────────────────────────────────────
    print("Splitting training data (Non-IID)...")

    all_files = {}
    for cls in CLASSES:
        files = sorted((train_dir / cls).glob('*'))
        files = [f for f in files if f.is_file()]
        random.shuffle(files)
        all_files[cls] = files

    total_train = sum(len(v) for v in all_files.values())
    per_hospital = total_train // HOSPITALS

    for h_idx in range(HOSPITALS):
        h_name = f'hospital_{h_idx + 1}'
        ratios = NONIID_RATIOS[h_name]

        for cls in CLASSES:
            ratio     = ratios[cls]
            n_files   = int(per_hospital * ratio)
            available = all_files[cls]

            # Take files from the front of the shuffled list
            assigned  = available[:n_files]
            all_files[cls] = available[n_files:]  # remove assigned files

            dest_cls_dir = dest / h_name / 'train' / cls
            for f in assigned:
                shutil.copy2(f, dest_cls_dir / f.name)

            print(f"  {h_name} / train / {cls}: {len(assigned)} files ({ratio*100:.0f}%)")

    # ── Copy VAL and TEST to all hospitals (shared) ───────────────────────────
    for split_name, split_src in [('val', val_dir), ('test', test_dir)]:
        print(f"\nCopying {split_name} to all hospitals...")
        for cls in CLASSES:
            files = [f for f in sorted((split_src / cls).glob('*')) if f.is_file()]
            for h in range(1, HOSPITALS + 1):
                dest_cls = dest / f'hospital_{h}' / split_name / cls
                for f in files:
                    shutil.copy2(f, dest_cls / f.name)
            print(f"  {split_name}/{cls}: {len(files)} files → all hospitals")

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'='*55}")
    print(f"  Non-IID Split Summary")
    print(f"{'='*55}")
    print(f"  {'Hospital':<14} {'PNEUMONIA':>12} {'NORMAL':>10} {'Total':>8} {'Ratio':>10}")
    print(f"  {'-'*54}")
    for h in range(1, HOSPITALS + 1):
        h_name = f'hospital_{h}'
        p_count = len(list((dest / h_name / 'train' / 'PNEUMONIA').glob('*')))
        n_count = len(list((dest / h_name / 'train' / 'NORMAL').glob('*')))
        total   = p_count + n_count
        ratio   = f"{p_count/(total+1e-8)*100:.0f}%P/{n_count/(total+1e-8)*100:.0f}%N"
        print(f"  {h_name:<14} {p_count:>12} {n_count:>10} {total:>8} {ratio:>10}")

    print(f"\nSaved to: {dest.resolve()}")
    print(f"\nTo use non-IID data, set in hospital agent:")
    for h in range(1, HOSPITALS + 1):
        print(f"  hospital_{h}: LOCAL_DATASET_PATH = \"{(dest / f'hospital_{h}').resolve()}\"")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Non-IID dataset split for federated learning research'
    )
    parser.add_argument('--source', required=True,
                        help='Path to chest_xray folder (train/, val/, test/)')
    parser.add_argument('--dest', default='./data/hospitals_noniid',
                        help='Output folder (default: ./data/hospitals_noniid)')
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()

    split_noniid(args.source, args.dest, args.seed)