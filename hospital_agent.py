"""
hospital_agent.py
=================
Runs on the hospital machine. Polls the Flask server for training jobs,
trains the model locally with Differential Privacy, and auto-submits weights.

Usage:
    python hospital_agent.py --hospital-id hospital_1 --server http://localhost:5000
    python hospital_agent.py --hospital-id hospital_1 --no-dp   (disable DP for ablation)
"""

import os
import sys
import json
import time
import math
import hashlib
import logging
import argparse
import requests
import io

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from torchvision import transforms, models
from torchvision.datasets import ImageFolder
from sklearn.metrics import (
    accuracy_score, precision_score,
    recall_score, f1_score, roc_auc_score
)

# ── LOGGING ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger('hospital_agent')

# ── DP CONFIG ─────────────────────────────────────────────────────────────────
DP_ENABLED       = True
CLIP_NORM        = 1.0
NOISE_MULTIPLIER = 0.01


# ── MODEL ─────────────────────────────────────────────────────────────────────

class PneumoniaModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.model = models.resnet18(weights=models.ResNet18_Weights.IMAGENET1K_V1)
        self.model.fc = nn.Linear(self.model.fc.in_features, 2)

    def forward(self, x):
        return self.model(x)


# ── DIFFERENTIAL PRIVACY ──────────────────────────────────────────────────────

def apply_differential_privacy(state_dict: dict, clip_norm: float,
                                noise_multiplier: float) -> dict:
    """
    Apply Gaussian noise to model weights for differential privacy.

    Steps:
      1. Clip each weight tensor by L2 norm (bounds sensitivity)
      2. Add calibrated Gaussian noise: N(0, (noise_multiplier * clip_norm)^2)

    This prevents the server from reverse-engineering patient data from weights.
    Standard DP-SGD weight perturbation mechanism.
    """
    noisy_state_dict = {}
    sigma = noise_multiplier * clip_norm

    for key, param in state_dict.items():
        if param.dtype in (torch.float32, torch.float64):
            param_norm  = param.norm(2).item()
            clip_factor = min(1.0, clip_norm / (param_norm + 1e-8))
            clipped     = param * clip_factor
            noise       = torch.randn_like(clipped) * sigma
            noisy_state_dict[key] = clipped + noise
        else:
            noisy_state_dict[key] = param.clone()

    return noisy_state_dict


def compute_epsilon(noise_multiplier: float, num_samples: int,
                    batch_size: int, epochs: int, delta: float = 1e-5) -> float:
    """Approximate privacy budget epsilon (simplified Gaussian mechanism)."""
    try:
        steps   = (num_samples / batch_size) * epochs
        epsilon = (math.sqrt(2 * math.log(1.25 / delta)) * steps) / \
                  (noise_multiplier * num_samples)
        return round(epsilon, 4)
    except Exception:
        return -1.0


# ── AGENT ─────────────────────────────────────────────────────────────────────

class HospitalAgent:

    def __init__(self, hospital_id: str, server_url: str, api_key: str):
        self.hospital_id   = hospital_id
        self.server_url    = server_url.rstrip('/')
        self.api_key       = api_key
        self.device        = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.poll_interval = 3

        logger.info("Hospital Agent started")
        logger.info(f"  Hospital            : {hospital_id}")
        logger.info(f"  Server              : {server_url}")
        logger.info(f"  Device              : {self.device}")
        logger.info(f"  Differential Privacy: {'ENABLED' if DP_ENABLED else 'DISABLED'}")
        if DP_ENABLED:
            logger.info(f"  Clip Norm           : {CLIP_NORM}")
            logger.info(f"  Noise Multiplier    : {NOISE_MULTIPLIER}")
        logger.info(f"Polling for jobs every {self.poll_interval}s...")

    def run(self):
        while True:
            try:
                self._send_heartbeat()
                job = self._poll_for_job()
                if job and job.get('status') == 'pending':
                    logger.info(f"New job | disease={job['disease_name']} | round={job['round']}")
                    self._run_job(job)
                else:
                    time.sleep(self.poll_interval)
            except KeyboardInterrupt:
                logger.info("Agent stopped.")
                break
            except Exception as e:
                logger.error(f"Main loop error: {str(e)}")
                time.sleep(self.poll_interval)

    def _send_heartbeat(self):
        """Ping server to show agent is online."""
        try:
            requests.post(
                f'{self.server_url}/api/agent-heartbeat',
                json={'hospital_id': self.hospital_id},
                timeout=5
            )
        except Exception:
            pass

    def _poll_for_job(self):
        try:
            r = requests.get(f'{self.server_url}/api/my-job/{self.hospital_id}', timeout=10)
            if r.status_code == 200:
                return r.json().get('job')
        except requests.exceptions.ConnectionError:
            logger.warning(f"Cannot connect to {self.server_url}. Retrying...")
        except Exception as e:
            logger.warning(f"Poll failed: {str(e)}")
        return None

    def _post_progress(self, status, current_epoch=0, total_epochs=0,
                       accuracy=None, loss=None, log=None, error=None):
        try:
            requests.post(
                f'{self.server_url}/api/job-progress',
                json={
                    'hospital_id':   self.hospital_id,
                    'status':        status,
                    'current_epoch': current_epoch,
                    'total_epochs':  total_epochs,
                    'accuracy':      accuracy,
                    'loss':          loss,
                    'log':           log,
                    'error':         error,
                },
                timeout=10
            )
        except Exception:
            pass

    def _run_job(self, job: dict):
        dataset_path = job['dataset_path']
        epochs       = job['epochs']
        round_num    = job['round']
        disease      = job['disease_domain']

        self._post_progress(
            status='training', current_epoch=0, total_epochs=epochs,
            log=f"Starting | disease={disease} | round={round_num} | DP={'ON' if DP_ENABLED else 'OFF'}"
        )

        try:
            # ── DATASET ──────────────────────────────────────────────────────
            transform = transforms.Compose([
                transforms.Resize((224, 224)),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406],
                                     std=[0.229, 0.224, 0.225])
            ])

            for split in ['train', 'val', 'test']:
                d = os.path.join(dataset_path, split)
                if not os.path.exists(d):
                    raise FileNotFoundError(
                        f"Missing {split}/ in: {dataset_path}\n"
                        f"Run: python scripts/split_dataset.py first"
                    )

            train_dataset = ImageFolder(os.path.join(dataset_path, 'train'), transform=transform)
            val_dataset   = ImageFolder(os.path.join(dataset_path, 'val'),   transform=transform)
            test_dataset  = ImageFolder(os.path.join(dataset_path, 'test'),  transform=transform)

            train_loader = DataLoader(train_dataset, batch_size=32, shuffle=True,  num_workers=0)
            val_loader   = DataLoader(val_dataset,   batch_size=32, shuffle=False, num_workers=0)
            test_loader  = DataLoader(test_dataset,  batch_size=32, shuffle=False, num_workers=0)

            num_train_samples = len(train_dataset)
            logger.info(f"Dataset: {num_train_samples} train | {len(val_dataset)} val | {len(test_dataset)} test")
            self._post_progress(
                status='training', current_epoch=0, total_epochs=epochs,
                log=f"Dataset loaded | train={num_train_samples} | val={len(val_dataset)} | test={len(test_dataset)}"
            )

            # ── MODEL ────────────────────────────────────────────────────────
            model = PneumoniaModel().to(self.device)

            if round_num >= 2:
                logger.info("Downloading global model from server...")
                path = self._download_global_model()
                if path:
                    try:
                        model.load_state_dict(torch.load(path, map_location=self.device))
                        # Reset batch norm running stats to match local data distribution.
                        # Prevents NaN loss when global model BN stats don't match local data.
                        for module in model.modules():
                            if isinstance(module, torch.nn.BatchNorm2d):
                                module.reset_running_stats()
                        logger.info(f"Loaded global model: {path}")
                        self._post_progress(
                            status='training', current_epoch=0, total_epochs=epochs,
                            log=f"Loaded aggregated global model for round {round_num}"
                        )
                    except Exception as e:
                        logger.warning(f"Could not load global model: {e}. Using fresh model.")
                else:
                    logger.warning("No global model available. Using fresh ResNet-18.")

            # ── TRAINING LOOP ────────────────────────────────────────────────
            # Lower LR for round 2+ since we start from aggregated weights
            lr        = 1e-4 if round_num == 1 else 5e-5
            optimizer = optim.Adam(model.parameters(), lr=lr)
            criterion = nn.CrossEntropyLoss()

            for epoch in range(1, epochs + 1):
                model.train()
                epoch_loss = correct = total = 0

                for images, labels in train_loader:
                    images, labels = images.to(self.device), labels.to(self.device)
                    optimizer.zero_grad()
                    outputs = model(images)
                    loss    = criterion(outputs, labels)
                    loss.backward()
                    # Gradient clipping prevents explosion from noisy starting weights
                    torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
                    optimizer.step()

                    epoch_loss += loss.item() * images.size(0)
                    preds       = torch.argmax(outputs, dim=1)
                    correct    += (preds == labels).sum().item()
                    total      += labels.size(0)

                avg_loss = epoch_loss / total
                acc      = correct / total
                val_m    = self._evaluate(model, val_loader, criterion)

                log_line = (
                    f"Epoch {epoch}/{epochs} | "
                    f"loss={avg_loss:.4f} acc={acc*100:.2f}% | "
                    f"val_loss={val_m['loss']:.4f} val_acc={val_m['accuracy']*100:.2f}%"
                )
                logger.info(log_line)
                self._post_progress(
                    status='training', current_epoch=epoch, total_epochs=epochs,
                    accuracy=round(acc, 4), loss=round(avg_loss, 4), log=log_line
                )

            # ── TEST EVALUATION ───────────────────────────────────────────────
            logger.info("Evaluating on test set...")
            test_m = self._evaluate(model, test_loader, criterion)
            test_m['num_samples'] = num_train_samples

            logger.info(
                f"Test | acc={test_m['accuracy']*100:.2f}% | "
                f"loss={test_m['loss']:.4f} | f1={test_m['f1_score']:.4f}"
            )
            self._post_progress(
                status='training', current_epoch=epochs, total_epochs=epochs,
                accuracy=test_m['accuracy'], loss=test_m['loss'],
                log=f"Test complete | acc={test_m['accuracy']*100:.2f}% | f1={test_m['f1_score']:.4f}"
            )

            # ── DIFFERENTIAL PRIVACY ──────────────────────────────────────────
            state_dict = model.state_dict()
            dp_info    = {'enabled': False}

            if DP_ENABLED:
                logger.info(f"Applying DP | clip={CLIP_NORM} | noise={NOISE_MULTIPLIER}")
                self._post_progress(
                    status='training', current_epoch=epochs, total_epochs=epochs,
                    log=f"Applying DP noise | clip_norm={CLIP_NORM} | noise_multiplier={NOISE_MULTIPLIER}"
                )

                state_dict = apply_differential_privacy(state_dict, CLIP_NORM, NOISE_MULTIPLIER)
                epsilon    = compute_epsilon(NOISE_MULTIPLIER, num_train_samples, 32, epochs)

                dp_info = {
                    'enabled':          True,
                    'clip_norm':        CLIP_NORM,
                    'noise_multiplier': NOISE_MULTIPLIER,
                    'epsilon':          epsilon,
                    'delta':            1e-5,
                    'mechanism':        'Gaussian'
                }
                logger.info(f"DP applied | epsilon={epsilon} | delta=1e-5")
                self._post_progress(
                    status='training', current_epoch=epochs, total_epochs=epochs,
                    log=f"DP applied | epsilon={epsilon} (lower=more private)"
                )

            # ── SAVE + SUBMIT ─────────────────────────────────────────────────
            buf = io.BytesIO()
            torch.save(state_dict, buf)
            weights_bytes = buf.getvalue()

            w_hash = hashlib.sha256(weights_bytes).hexdigest()
            logger.info(f"Weights ready | {len(weights_bytes)/(1024*1024):.2f}MB | {w_hash[:16]}...")

            self._post_progress(
                status='training', current_epoch=epochs, total_epochs=epochs,
                log="Submitting weights to server..."
            )

            result = self._submit_weights(weights_bytes, round_num, test_m, dp_info)

            if result['success']:
                agg  = result.get('aggregation_status', 'registered')
                recv = result.get('submissions_received', '?')
                exp  = result.get('submissions_expected', '?')
                msg  = f"Submitted | status={agg} | {recv}/{exp} hospitals"
                logger.info(msg)
                self._post_progress(
                    status='done', current_epoch=epochs, total_epochs=epochs,
                    accuracy=test_m['accuracy'], loss=test_m['loss'], log=msg
                )
                if agg == 'round_complete':
                    logger.info("ALL SUBMITTED — FedAvg triggered!")
            else:
                raise Exception(f"Submission failed: {result.get('error')}")

        except FileNotFoundError as e:
            msg = str(e)
            logger.error(msg)
            self._post_progress(status='failed', log=f"ERROR: {msg}", error=msg)

        except Exception as e:
            msg = str(e)
            logger.error(f"Training failed: {msg}")
            self._post_progress(status='failed', log=f"ERROR: {msg}", error=msg)

    def _evaluate(self, model, dataloader, criterion):
        model.eval()
        total_loss = 0.0
        y_true, y_pred, y_proba = [], [], []

        with torch.no_grad():
            for images, labels in dataloader:
                images, labels = images.to(self.device), labels.to(self.device)
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
        }

    def _download_global_model(self):
        try:
            r = requests.get(f'{self.server_url}/api/global-model/latest',
                             timeout=60, stream=True)
            if r.status_code == 200:
                rnd  = r.headers.get('X-GLOBAL-ROUND', 'latest')
                path = f'global_model_round{rnd}.pt'
                with open(path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
                return path
        except Exception as e:
            logger.warning(f"Download failed: {e}")
        return None

    def _submit_weights(self, weights_bytes, round_num, metrics, dp_info=None):
        try:
            payload = {
                'accuracy':    metrics['accuracy'],
                'loss':        metrics['loss'],
                'num_samples': metrics['num_samples'],
                'precision':   metrics.get('precision', metrics['accuracy']),
                'recall':      metrics.get('recall',    metrics['accuracy']),
                'f1_score':    metrics.get('f1_score',  metrics['accuracy']),
                'auc_roc':     metrics.get('auc_roc',   metrics['accuracy']),
            }
            if dp_info:
                payload['dp_info'] = dp_info

            r = requests.post(
                f'{self.server_url}/api/submit_update',
                files={'weights': (f'weights_r{round_num}.pt', weights_bytes,
                                   'application/octet-stream')},
                data={
                    'hospital_id': self.hospital_id,
                    'round':       str(round_num),
                    'metrics':     json.dumps(payload)
                },
                headers={'X-API-KEY': self.api_key},
                timeout=120
            )
            if r.status_code == 200:
                return {'success': True, **r.json()}
            return {'success': False, 'error': f'HTTP {r.status_code}: {r.text[:100]}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}


# ── ENTRY POINT ───────────────────────────────────────────────────────────────

def load_api_key(hospital_id, config_path='./config/hospitals.json'):
    try:
        with open(config_path) as f:
            tokens = json.load(f)
        key = tokens.get(hospital_id)
        if not key:
            raise KeyError(f"No token for {hospital_id}")
        return key
    except FileNotFoundError:
        logger.error(f"config/hospitals.json not found at {config_path}")
        sys.exit(1)
    except KeyError as e:
        logger.error(str(e))
        sys.exit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='MedLedger Hospital Agent')
    parser.add_argument('--hospital-id', required=True, help='e.g. hospital_1')
    parser.add_argument('--server', default='http://localhost:5000')
    parser.add_argument('--config', default='./config/hospitals.json')
    parser.add_argument('--no-dp', action='store_true', help='Disable DP (ablation study)')
    args = parser.parse_args()

    if args.no_dp:
        DP_ENABLED = False

    api_key = load_api_key(args.hospital_id, args.config)
    HospitalAgent(args.hospital_id, args.server, api_key).run()