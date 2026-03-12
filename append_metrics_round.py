#!/usr/bin/env python3
"""
Federated Learning Metrics Appender
====================================

This utility demonstrates how to append new training rounds to the metrics log.
As hospitals contribute datasets and federated learning continues, new rounds
are appended to create a continuous journey of model improvement.

Usage:
    python append_metrics_round.py --round <n> --accuracy <val> --precision <val> ...

This maintains historical records and enables continuous metrics tracking.
"""

import json
import os
from datetime import datetime
import argparse


def append_training_round(data_dir, round_num, timestamp=None, institutions=5, 
                          samples=20000, accuracy=0.90, precision=0.88,
                          recall=0.92, f1_score=0.90, loss=0.22, auc_roc=0.93):
    """
    Append a new training round to the metrics JSON.
    
    This function simulates continuous model improvement as new hospitals
    contribute data through federated learning rounds.
    """
    metrics_path = os.path.join(data_dir, 'federated_metrics.json')
    
    if not os.path.exists(metrics_path):
        raise FileNotFoundError(f"Metrics file not found at {metrics_path}")
    
    # Load existing metrics
    with open(metrics_path, 'r') as f:
        metrics = json.load(f)
    
    # Update timestamp
    if timestamp is None:
        timestamp = datetime.now().isoformat()
    
    metrics['last_updated'] = timestamp
    metrics['training_rounds'] = round_num
    
    # Append to per-round arrays
    metrics['accuracy_per_round'].append(accuracy)
    metrics['precision_per_round'].append(precision)
    metrics['recall_per_round'].append(recall)
    metrics['f1_score_per_round'].append(f1_score)
    metrics['loss_per_round'].append(loss)
    metrics['auc_roc_per_round'].append(auc_roc)
    
    # Update final metrics
    metrics['final_accuracy'] = accuracy * 100
    metrics['final_precision'] = precision * 100
    metrics['final_recall'] = recall * 100
    metrics['final_f1_score'] = f1_score
    metrics['final_loss'] = loss
    metrics['final_auc_roc'] = auc_roc * 100
    metrics['institutions_participated'] = institutions
    
    # Append to training history
    history_entry = {
        'round': round_num,
        'timestamp': timestamp,
        'institutions_participated': institutions,
        'samples_processed': samples,
        'accuracy': accuracy,
        'precision': precision,
        'recall': recall,
        'f1_score': f1_score,
        'loss': loss,
        'auc_roc': auc_roc
    }
    metrics['training_history'].append(history_entry)
    
    # Save updated metrics
    with open(metrics_path, 'w') as f:
        json.dump(metrics, f, indent=2)
    
    print(f"✓ Round {round_num} appended successfully")
    print(f"  - Accuracy: {accuracy * 100:.2f}%")
    print(f"  - Precision: {precision * 100:.2f}%")
    print(f"  - Recall: {recall * 100:.2f}%")
    print(f"  - F1 Score: {f1_score:.4f}")
    print(f"  - AUC-ROC: {auc_roc * 100:.2f}%")
    print(f"  - Loss: {loss:.4f}")
    print(f"  - Timestamp: {timestamp}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Append new training round to metrics')
    parser.add_argument('--round', type=int, required=True, help='Round number')
    parser.add_argument('--accuracy', type=float, default=0.90)
    parser.add_argument('--precision', type=float, default=0.88)
    parser.add_argument('--recall', type=float, default=0.92)
    parser.add_argument('--f1', type=float, default=0.90)
    parser.add_argument('--loss', type=float, default=0.22)
    parser.add_argument('--auc', type=float, default=0.93)
    parser.add_argument('--institutions', type=int, default=5)
    parser.add_argument('--samples', type=int, default=20000)
    parser.add_argument('--timestamp', type=str, default=None)
    
    args = parser.parse_args()
    
    data_dir = os.path.join(os.path.dirname(__file__), 'data')
    append_training_round(
        data_dir,
        round_num=args.round,
        accuracy=args.accuracy,
        precision=args.precision,
        recall=args.recall,
        f1_score=args.f1,
        loss=args.loss,
        auc_roc=args.auc,
        institutions=args.institutions,
        samples=args.samples,
        timestamp=args.timestamp
    )
