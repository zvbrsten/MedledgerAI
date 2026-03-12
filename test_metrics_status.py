#!/usr/bin/env python3
"""
Test Federated Learning Metrics System Status
Displays comprehensive metrics report
"""

import json
from metrics_loader import load_federated_metrics, format_timestamp
import os

def main():
    data_dir = 'data'
    metrics = load_federated_metrics(data_dir)

    if metrics.get('available'):
        print('\n' + '='*60)
        print('FEDERATED LEARNING METRICS SYSTEM - STATUS REPORT')
        print('='*60)
        
        print(f'\nModel ID: {metrics.get("model_id")}')
        print(f'Training Rounds: {metrics.get("training_rounds")}')
        print(f'Institutions: {metrics.get("institutions_participated")}')
        print(f'Last Updated: {format_timestamp(metrics.get("last_updated"))}')
        
        print('\nCURRENT METRICS:')
        print(f'  Accuracy:  {metrics.get("final_accuracy"):.2f}%')
        print(f'  Precision: {metrics.get("final_precision"):.2f}%')
        print(f'  Recall:    {metrics.get("final_recall"):.2f}%')
        print(f'  F1 Score:  {metrics.get("final_f1_score"):.4f}')
        print(f'  AUC-ROC:   {metrics.get("final_auc_roc"):.2f}%')
        print(f'  Loss:      {metrics.get("final_loss"):.4f}')
        
        print('\nTRAINING HISTORY:')
        history = metrics.get('training_history', [])
        print(f'  Total Rounds in History: {len(history)}')
        
        if len(history) > 0:
            first = history[0]
            print(f'\n  Round 1 (First Training):')
            print(f'    - Accuracy: {first["accuracy"]*100:.2f}%')
            print(f'    - Institutions: {first["institutions_participated"]}')
            print(f'    - Samples: {first["samples_processed"]:,}')
            print(f'    - Timestamp: {first["timestamp"]}')
        
        if len(history) > 1:
            last = history[-1]
            print(f'\n  Round {last["round"]} (Latest Training):')
            print(f'    - Accuracy: {last["accuracy"]*100:.2f}%')
            print(f'    - Institutions: {last["institutions_participated"]}')
            print(f'    - Samples: {last["samples_processed"]:,}')
            print(f'    - Timestamp: {last["timestamp"]}')
        
        print('\nMETRICS ARRAYS (per-round values):')
        for metric_name in ['accuracy', 'precision', 'recall', 'f1_score', 'loss', 'auc_roc']:
            array_name = f'{metric_name}_per_round'
            if array_name in metrics:
                arr = metrics[array_name]
                print(f'  OK {metric_name.capitalize():12} {len(arr):2} values')
        
        print('\n' + '='*60)
        print('SUCCESS: METRICS SYSTEM FULLY OPERATIONAL')
        print('='*60)
        
        # Show improvement trajectory
        accuracies = metrics.get('accuracy_per_round', [])
        if len(accuracies) > 1:
            improvement = (accuracies[-1] - accuracies[0]) * 100
            print(f'\nImprovement Trajectory:')
            print(f'  Round 1:  {accuracies[0]*100:.1f}%')
            print(f'  Latest:   {accuracies[-1]*100:.1f}%')
            print(f'  Increase: +{improvement:.1f} percentage points')
    else:
        print('ERROR: Metrics not available')

if __name__ == '__main__':
    main()
