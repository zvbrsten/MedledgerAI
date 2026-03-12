#!/usr/bin/env python3
"""Test script to verify metrics values are correct"""

from metrics_loader import load_federated_metrics
import json

# Test the metrics loading
metrics = load_federated_metrics('data')
print('✓ Metrics loaded successfully')
print(f'Available: {metrics.get("available")}')
print(f'Final Accuracy: {metrics.get("final_accuracy")}%')
print(f'Final Precision: {metrics.get("final_precision")}%')
print(f'Final Recall: {metrics.get("final_recall")}%')
print(f'Final AUC-ROC: {metrics.get("final_auc_roc")}')
print(f'Training History Records: {len(metrics.get("training_history", []))}')

# Verify arrays have different values
print()
print('Metric Arrays (per round):')
print('Accuracy: ', metrics.get('accuracy_per_round'))
print('Precision:', metrics.get('precision_per_round'))
print('Recall:   ', metrics.get('recall_per_round'))
print('AUC-ROC:  ', metrics.get('auc_roc_per_round'))

# Check if values are truly different
acc = metrics.get('accuracy_per_round', [])
prec = metrics.get('precision_per_round', [])
recall = metrics.get('recall_per_round', [])
f1 = metrics.get('f1_score_per_round', [])
auc = metrics.get('auc_roc_per_round', [])

print()
print('=== VALIDATION RESULTS ===')
if acc != prec:
    print('✓ Precision values are DIFFERENT from Accuracy')
else:
    print('✗ ERROR: Precision values are SAME as Accuracy')

if acc != recall:
    print('✓ Recall values are DIFFERENT from Accuracy')
else:
    print('✗ ERROR: Recall values are SAME as Accuracy')

if acc != f1:
    print('✓ F1 Score values are DIFFERENT from Accuracy')
else:
    print('✗ ERROR: F1 Score values are SAME as Accuracy')

if acc != auc:
    print('✓ AUC-ROC values are DIFFERENT from Accuracy')
else:
    print('✗ ERROR: AUC-ROC values are SAME as Accuracy')

# Verify training history
print()
print('=== TRAINING HISTORY VALIDATION ===')
history = metrics.get('training_history', [])
for i, h in enumerate(history):
    if h['accuracy'] != h['precision']:
        print(f'✓ Round {i+1}: Metrics are different')
    else:
        print(f'✗ Round {i+1}: ERROR - Metrics are the same')
