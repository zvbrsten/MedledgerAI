#!/usr/bin/env python3
"""Test script to verify metrics loading"""

import os
from metrics_loader import load_federated_metrics, format_timestamp

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
metrics_data = load_federated_metrics(DATA_DIR)

print(f"Metrics available: {metrics_data.get('available')}")

if metrics_data.get('available'):
    status = {
        'model_available': True,
        'rounds_completed': metrics_data.get('training_rounds', 0),
        'accuracy': f"{metrics_data.get('final_accuracy', 0):.2f}%",
        'loss': f"{metrics_data.get('final_loss', 0):.4f}" if metrics_data.get('final_loss') else 'N/A',
        'last_updated': format_timestamp(metrics_data.get('last_updated', '')),
        'accuracy_array': metrics_data.get('accuracy_per_round', []),
        'loss_array': metrics_data.get('loss_per_round', []),
        'model_id': metrics_data.get('model_id', 'medledger_global'),
        'institutions': metrics_data.get('institutions_participated', 0)
    }
    print(f'✓ Status object created successfully')
    print(f'  - Rounds: {status["rounds_completed"]}')
    print(f'  - Accuracy: {status["accuracy"]}')
    print(f'  - Loss: {status["loss"]}')
    print(f'  - Last Updated: {status["last_updated"]}')
    print(f'  - Accuracy array length: {len(status["accuracy_array"])}')
    print(f'  - Loss array length: {len(status["loss_array"])}')
else:
    print("✗ Metrics not available")
