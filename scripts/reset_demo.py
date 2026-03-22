"""
scripts/reset_demo.py
=====================
Resets all FL state for a clean demo run.

What it clears:
  - data/round_state.json         → round 1, no submissions
  - models/incoming/              → emptied
  - models/global/                → emptied
  - data/federated_metrics.json   → zeroed out

Usage:
    python scripts/reset_demo.py
    python scripts/reset_demo.py --yes    # skip confirmation prompt

Run this before each demo to start fresh.
"""

import os
import sys
import json
import shutil
import argparse
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent.parent


def reset(yes: bool = False):
    if not yes:
        print("This will clear ALL federated learning data (rounds, weights, metrics).")
        confirm = input("Type 'yes' to confirm: ").strip().lower()
        if confirm != "yes":
            print("Aborted.")
            sys.exit(0)

    print("\nResetting demo state...")

    # ── Round state ───────────────────────────────────────────────────────────
    state_file = ROOT / "data" / "round_state.json"
    state_file.parent.mkdir(exist_ok=True)
    clean_state = {
        "current_round": 1,
        "expected_hospitals": 5,
        "received_updates": [],
        "submissions": {},
        "aggregation_status": "pending",
        "last_aggregation": None,
        "created_at": datetime.utcnow().isoformat() + "Z"
    }
    with open(state_file, "w") as f:
        json.dump(clean_state, f, indent=2)
    print("  ✓ data/round_state.json reset to round 1")

    # ── Incoming models ───────────────────────────────────────────────────────
    incoming_dir = ROOT / "models" / "incoming"
    if incoming_dir.exists():
        shutil.rmtree(incoming_dir)
    incoming_dir.mkdir(parents=True)
    print("  ✓ models/incoming/ cleared")

    # ── Global models ─────────────────────────────────────────────────────────
    global_dir = ROOT / "models" / "global"
    if global_dir.exists():
        shutil.rmtree(global_dir)
    global_dir.mkdir(parents=True)
    print("  ✓ models/global/ cleared")

    # ── Federated metrics ─────────────────────────────────────────────────────
    metrics_file = ROOT / "data" / "federated_metrics.json"
    empty_metrics = {
        "model_id": "medledger_global_v1",
        "last_updated": datetime.utcnow().isoformat(),
        "institutions_participated": 5,
        "training_rounds": 0,
        "accuracy_per_round": [],
        "precision_per_round": [],
        "recall_per_round": [],
        "f1_score_per_round": [],
        "loss_per_round": [],
        "auc_roc_per_round": [],
        "final_accuracy": 0,
        "final_precision": 0,
        "final_recall": 0,
        "final_f1_score": 0,
        "final_loss": 0,
        "final_auc_roc": 0,
        "model_status": "not_trained",
        "training_history": []
    }
    with open(metrics_file, "w") as f:
        json.dump(empty_metrics, f, indent=2)
    print("  ✓ data/federated_metrics.json zeroed out")

    print("\n✓ Demo reset complete. Ready for round 1.")
    print("  Run: python app.py")
    print("  Then: python scripts/demo_run.py --round 1\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reset demo FL state")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()
    reset(args.yes)
