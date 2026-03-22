"""
scripts/demo_run.py
===================
Quick demo submission script.

Submits fake model weights from all 5 hospitals to the Flask server
WITHOUT running actual training. Useful for demoing the full FL flow
(submission → aggregation → blockchain logging) quickly.

Usage:
    python scripts/demo_run.py                    # submit round 1, all hospitals
    python scripts/demo_run.py --round 2          # submit round 2
    python scripts/demo_run.py --hospital hospital_1   # single hospital only
    python scripts/demo_run.py --round 1 --delay 2     # 2 sec between submissions

Requirements:
    Flask server must be running: python app.py
"""

import os
import sys
import json
import time
import struct
import random
import hashlib
import argparse
import requests
from pathlib import Path

# ── CONFIG ────────────────────────────────────────────────────────────────────

SERVER_URL    = "http://localhost:5000"
CONFIG_PATH   = Path(__file__).parent.parent / "config" / "hospitals.json"
HOSPITALS     = [f"hospital_{i}" for i in range(1, 6)]

# Realistic fake metrics per hospital (slightly different to show variation)
FAKE_METRICS = {
    "hospital_1": {"accuracy": 0.8721, "loss": 0.3412, "num_samples": 1044,
                   "precision": 0.8534, "recall": 0.8899, "f1_score": 0.8713, "auc_roc": 0.9201},
    "hospital_2": {"accuracy": 0.8563, "loss": 0.3789, "num_samples": 1043,
                   "precision": 0.8401, "recall": 0.8712, "f1_score": 0.8554, "auc_roc": 0.9045},
    "hospital_3": {"accuracy": 0.8812, "loss": 0.3201, "num_samples": 1044,
                   "precision": 0.8655, "recall": 0.8934, "f1_score": 0.8792, "auc_roc": 0.9312},
    "hospital_4": {"accuracy": 0.8634, "loss": 0.3654, "num_samples": 1043,
                   "precision": 0.8478, "recall": 0.8791, "f1_score": 0.8632, "auc_roc": 0.9123},
    "hospital_5": {"accuracy": 0.8745, "loss": 0.3389, "num_samples": 1042,
                   "precision": 0.8589, "recall": 0.8912, "f1_score": 0.8748, "auc_roc": 0.9234},
}

# Simulate improvement in later rounds
ROUND_BOOST = {1: 0.0, 2: 0.015, 3: 0.025, 4: 0.030}


def load_tokens():
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def make_fake_weights(hospital_id: str, round_num: int, num_samples: int = 1000) -> bytes:
    """
    Create a valid PyTorch state dict that mimics a ResNet-18.
    Small tensors instead of full size — valid for torch.load() and FedAvg.
    """
    import torch
    import io

    random.seed(hashlib.md5(f"{hospital_id}_{round_num}".encode()).hexdigest())

    # Minimal state dict that matches ResNet-18 layer names
    # Using tiny tensors (1x1) instead of full size — valid for averaging
    state_dict = {
        'model.conv1.weight':      torch.randn(64, 3, 7, 7)   * 0.01,
        'model.bn1.weight':        torch.ones(64),
        'model.bn1.bias':          torch.zeros(64),
        'model.bn1.running_mean':  torch.zeros(64),
        'model.bn1.running_var':   torch.ones(64),
        'model.bn1.num_batches_tracked': torch.tensor(0),
        'model.fc.weight':         torch.randn(2, 512) * 0.01,
        'model.fc.bias':           torch.zeros(2),
    }

    # Add noise per hospital so weights are slightly different
    noise_scale = 0.001 * (int(hospital_id.split('_')[1]))
    for k in state_dict:
        if state_dict[k].dtype == torch.float32:
            state_dict[k] = state_dict[k] + torch.randn_like(state_dict[k]) * noise_scale

    buffer = io.BytesIO()
    torch.save(state_dict, buffer)
    return buffer.getvalue()

def submit_hospital(hospital_id: str, round_num: int, api_key: str, delay: float = 0):
    """Submit fake weights for one hospital."""
    if delay > 0:
        time.sleep(delay)

    base_metrics = FAKE_METRICS.get(hospital_id, FAKE_METRICS["hospital_1"]).copy()
    boost = ROUND_BOOST.get(round_num, 0.03)
    boost += random.uniform(-0.005, 0.005)  # small noise

    metrics = {
        "accuracy":    min(0.99, base_metrics["accuracy"]   + boost),
        "loss":        max(0.10, base_metrics["loss"]        - boost * 0.5),
        "num_samples": base_metrics["num_samples"],
        "precision":   min(0.99, base_metrics["precision"]  + boost),
        "recall":      min(0.99, base_metrics["recall"]     + boost),
        "f1_score":    min(0.99, base_metrics["f1_score"]   + boost),
        "auc_roc":     min(0.99, base_metrics["auc_roc"]    + boost * 0.5),
    }

    # Round to 4 decimal places
    metrics = {k: round(v, 4) if isinstance(v, float) else v for k, v in metrics.items()}

    fake_weights = make_fake_weights(hospital_id, round_num, metrics["num_samples"])

    print(f"  Submitting {hospital_id} round {round_num}...", end=" ", flush=True)

    try:
        response = requests.post(
            f"{SERVER_URL}/api/submit_update",
            files={"weights": (f"local_model_round{round_num}.pt", fake_weights, "application/octet-stream")},
            data={
                "hospital_id": hospital_id,
                "round": round_num,
                "metrics": json.dumps(metrics)
            },
            headers={"X-API-KEY": api_key},
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            agg_status = data.get("aggregation_status", "?")
            received   = data.get("submissions_received", "?")
            expected   = data.get("submissions_expected", "?")
            print(f"✓ [{received}/{expected}] status={agg_status} "
                  f"accuracy={metrics['accuracy']*100:.2f}%")
            return True
        else:
            print(f"✗ HTTP {response.status_code}: {response.text[:100]}")
            return False

    except requests.exceptions.ConnectionError:
        print(f"✗ Cannot connect to {SERVER_URL}. Is Flask running?")
        return False
    except Exception as e:
        print(f"✗ Error: {str(e)}")
        return False


def run_demo(round_num: int, target_hospitals: list, delay: float):
    print(f"\n{'='*60}")
    print(f"  DEMO RUN — Round {round_num}")
    print(f"  Hospitals: {', '.join(target_hospitals)}")
    print(f"  Server: {SERVER_URL}")
    print(f"{'='*60}\n")

    tokens = load_tokens()
    results = []

    for hospital_id in target_hospitals:
        api_key = tokens.get(hospital_id)
        if not api_key:
            print(f"  ✗ No API key for {hospital_id}")
            results.append(False)
            continue

        success = submit_hospital(hospital_id, round_num, api_key, delay if results else 0)
        results.append(success)

    passed = sum(results)
    print(f"\n{'='*60}")
    print(f"  Result: {passed}/{len(results)} submissions successful")
    if passed == len(results):
        print(f"  ✓ All hospitals submitted. FedAvg should have triggered.")
        print(f"  Check /admin and /blockchain-ledger in the browser.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Demo submission script — submits fake weights from hospitals"
    )
    parser.add_argument("--round",    type=int,   default=1,
                        help="FL round number (default: 1)")
    parser.add_argument("--hospital", type=str,   default=None,
                        help="Single hospital ID (default: all 5)")
    parser.add_argument("--delay",    type=float, default=1.0,
                        help="Seconds between submissions (default: 1.0)")
    parser.add_argument("--server",   type=str,   default=SERVER_URL,
                        help=f"Flask server URL (default: {SERVER_URL})")

    args = parser.parse_args()
    SERVER_URL = args.server

    if args.hospital:
        if args.hospital not in HOSPITALS:
            print(f"Unknown hospital: {args.hospital}. Valid: {', '.join(HOSPITALS)}")
            sys.exit(1)
        targets = [args.hospital]
    else:
        targets = HOSPITALS

    run_demo(args.round, targets, args.delay)
