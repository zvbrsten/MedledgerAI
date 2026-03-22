"""
scripts/split_dataset.py
========================
Splits the Kaggle chest_xray dataset into 5 hospital folders.

Each hospital gets a disjoint subset of the training data.
Val and test sets are shared (each hospital gets a copy for local evaluation).

Usage:
    python scripts/split_dataset.py --source /path/to/chest_xray --dest ./data/hospitals

After running you get:
    data/hospitals/
        hospital_1/train/NORMAL/...  hospital_1/train/PNEUMONIA/...
        hospital_1/val/...           hospital_1/test/...
        hospital_2/train/...
        ...
        hospital_5/train/...

Then in the notebook set:
    LOCAL_DATASET_PATH = "./data/hospitals/hospital_1"
"""

import os
import shutil
import random
import argparse
from pathlib import Path


HOSPITALS = 5
CLASSES   = ["NORMAL", "PNEUMONIA"]
SPLITS    = ["train", "val", "test"]


def split_dataset(source_dir: str, dest_dir: str, seed: int = 42):
    source = Path(source_dir)
    dest   = Path(dest_dir)

    # Validate source structure
    train_dir = source / "train"
    val_dir   = source / "val"
    test_dir  = source / "test"

    for d in [train_dir, val_dir, test_dir]:
        if not d.exists():
            raise FileNotFoundError(f"Missing directory: {d}")

    # Create destination folders
    for h in range(1, HOSPITALS + 1):
        for split in SPLITS:
            for cls in CLASSES:
                (dest / f"hospital_{h}" / split / cls).mkdir(parents=True, exist_ok=True)

    random.seed(seed)

    # ── Split TRAIN data (disjoint across hospitals) ──────────────────────────
    print("Splitting training data...")
    for cls in CLASSES:
        files = sorted((train_dir / cls).glob("*"))
        files = [f for f in files if f.is_file()]
        random.shuffle(files)

        chunks = [[] for _ in range(HOSPITALS)]
        for i, f in enumerate(files):
            chunks[i % HOSPITALS].append(f)

        for h_idx, chunk in enumerate(chunks):
            h_name = f"hospital_{h_idx + 1}"
            dest_cls_dir = dest / h_name / "train" / cls
            for f in chunk:
                shutil.copy2(f, dest_cls_dir / f.name)
            print(f"  {h_name} / train / {cls}: {len(chunk)} files")

    # ── Copy VAL and TEST to each hospital (shared) ───────────────────────────
    for split_name, split_src in [("val", val_dir), ("test", test_dir)]:
        print(f"Copying {split_name} data to all hospitals...")
        for cls in CLASSES:
            files = sorted((split_src / cls).glob("*"))
            files = [f for f in files if f.is_file()]
            for h in range(1, HOSPITALS + 1):
                dest_cls_dir = dest / f"hospital_{h}" / split_name / cls
                for f in files:
                    shutil.copy2(f, dest_cls_dir / f.name)
            print(f"  {split_name} / {cls}: {len(files)} files → all hospitals")

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n=== Split Summary ===")
    for h in range(1, HOSPITALS + 1):
        h_name = f"hospital_{h}"
        total  = sum(
            len(list((dest / h_name / s / c).glob("*")))
            for s in SPLITS for c in CLASSES
        )
        train_total = sum(
            len(list((dest / h_name / "train" / c).glob("*")))
            for c in CLASSES
        )
        print(f"  {h_name}: {train_total} train images, {total} total")

    print(f"\nDone. Hospital data saved to: {dest.resolve()}")
    print("\nIn the notebook, set:")
    for h in range(1, HOSPITALS + 1):
        print(f"  hospital_{h}: LOCAL_DATASET_PATH = \"{(dest / f'hospital_{h}').resolve()}\"")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Split chest_xray dataset into 5 hospital folders")
    parser.add_argument(
        "--source",
        type=str,
        required=True,
        help="Path to original chest_xray folder (must contain train/, val/, test/)"
    )
    parser.add_argument(
        "--dest",
        type=str,
        default="./data/hospitals",
        help="Destination folder for split data (default: ./data/hospitals)"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducible split (default: 42)"
    )

    args = parser.parse_args()
    split_dataset(args.source, args.dest, args.seed)
