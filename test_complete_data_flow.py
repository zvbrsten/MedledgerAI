#!/usr/bin/env python3
"""
End-to-End Data Flow Test
Tests the complete pipeline: JSON → Loader → Flask → Template Display
"""

import json
from metrics_loader import load_federated_metrics

def test_json_structure():
    """Test that JSON file is valid and contains all required fields"""
    print("\n1. JSON FILE STRUCTURE TEST")
    print("-" * 60)
    
    try:
        with open('data/federated_metrics.json', 'r') as f:
            data = json.load(f)
        print("✓ JSON file is valid and parseable")
        
        required_fields = [
            'model_id', 'last_updated', 'institutions_participated',
            'training_rounds', 'accuracy_per_round', 'precision_per_round',
            'recall_per_round', 'f1_score_per_round', 'auc_roc_per_round',
            'loss_per_round', 'final_accuracy', 'final_precision',
            'final_recall', 'final_auc_roc', 'final_loss', 'training_history'
        ]
        
        missing = [f for f in required_fields if f not in data]
        if missing:
            print(f"✗ Missing fields: {missing}")
            return False
        
        print(f"✓ All {len(required_fields)} required fields present")
        return True
    
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def test_metrics_loader():
    """Test that metrics_loader correctly reads the JSON"""
    print("\n2. METRICS LOADER TEST")
    print("-" * 60)
    
    try:
        metrics = load_federated_metrics('data')
        
        if not metrics.get('available'):
            print("✗ Metrics marked as unavailable")
            return False
        
        print("✓ Metrics loader successfully read JSON")
        
        # Check critical values
        checks = [
            ('Model ID', metrics.get('model_id'), 'medledger_global_v1'),
            ('Training Rounds', metrics.get('training_rounds'), 5),
            ('Institutions', metrics.get('institutions_participated'), 5),
        ]
        
        all_ok = True
        for check_name, actual, expected in checks:
            if actual == expected:
                print(f"✓ {check_name}: {actual}")
            else:
                print(f"✗ {check_name}: expected {expected}, got {actual}")
                all_ok = False
        
        return all_ok
    
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def test_metric_distinctness():
    """Test that metrics have distinct, realistic values"""
    print("\n3. METRIC DISTINCTNESS TEST")
    print("-" * 60)
    
    try:
        metrics = load_federated_metrics('data')
        
        acc = metrics.get('accuracy_per_round', [])
        prec = metrics.get('precision_per_round', [])
        recall = metrics.get('recall_per_round', [])
        f1 = metrics.get('f1_score_per_round', [])
        auc = metrics.get('auc_roc_per_round', [])
        
        checks = [
            ('Precision != Accuracy', acc != prec),
            ('Recall != Accuracy', acc != recall),
            ('F1 != Accuracy', acc != f1),
            ('AUC-ROC != Accuracy', acc != auc),
            ('Precision != Recall', prec != recall),
            ('Recall != AUC-ROC', recall != auc),
        ]
        
        all_ok = True
        for check_name, result in checks:
            if result:
                print(f"✓ {check_name}")
            else:
                print(f"✗ {check_name}")
                all_ok = False
        
        return all_ok
    
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def test_metric_ranges():
    """Test that metrics are in realistic ranges (0.0 to 1.0)"""
    print("\n4. METRIC RANGES TEST")
    print("-" * 60)
    
    try:
        metrics = load_federated_metrics('data')
        
        arrays = {
            'Accuracy': metrics.get('accuracy_per_round', []),
            'Precision': metrics.get('precision_per_round', []),
            'Recall': metrics.get('recall_per_round', []),
            'F1 Score': metrics.get('f1_score_per_round', []),
            'AUC-ROC': metrics.get('auc_roc_per_round', []),
            'Loss': metrics.get('loss_per_round', []),
        }
        
        all_ok = True
        for metric_name, values in arrays.items():
            all_in_range = all(0 <= v <= 1 for v in values)
            if all_in_range:
                min_val = min(values)
                max_val = max(values)
                print(f"✓ {metric_name}: {min_val:.4f} - {max_val:.4f}")
            else:
                print(f"✗ {metric_name}: out of range")
                all_ok = False
        
        return all_ok
    
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def test_training_history():
    """Test that training history records have distinct metrics"""
    print("\n5. TRAINING HISTORY TEST")
    print("-" * 60)
    
    try:
        metrics = load_federated_metrics('data')
        history = metrics.get('training_history', [])
        
        if len(history) != 5:
            print(f"✗ Expected 5 history records, got {len(history)}")
            return False
        
        print(f"✓ Found {len(history)} training history records")
        
        all_ok = True
        for i, record in enumerate(history):
            round_num = record.get('round', i + 1)
            acc = record.get('accuracy')
            prec = record.get('precision')
            recall = record.get('recall')
            f1 = record.get('f1_score')
            auc = record.get('auc_roc')
            
            # Check all metrics are present
            if all(x is not None for x in [acc, prec, recall, f1, auc]):
                # Check they're distinct
                if acc != prec and acc != recall and prec != recall:
                    print(f"✓ Round {round_num}: All metrics distinct")
                else:
                    print(f"✗ Round {round_num}: Metrics not distinct")
                    all_ok = False
            else:
                print(f"✗ Round {round_num}: Missing metric values")
                all_ok = False
        
        return all_ok
    
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def test_template_compatibility():
    """Test that data structure matches template expectations"""
    print("\n6. TEMPLATE COMPATIBILITY TEST")
    print("-" * 60)
    
    try:
        metrics = load_federated_metrics('data')
        
        # Simulate what the Flask template expects
        expected_keys = [
            'accuracy_per_round',
            'precision_per_round', 
            'recall_per_round',
            'f1_score_per_round',
            'auc_roc_per_round',
            'loss_per_round',
            'training_history'
        ]
        
        all_ok = True
        for key in expected_keys:
            if key in metrics:
                print(f"✓ Template key available: {key}")
            else:
                print(f"✗ Template key missing: {key}")
                all_ok = False
        
        # Check training history structure
        history = metrics.get('training_history', [])
        if history:
            sample = history[0]
            history_keys = ['round', 'timestamp', 'accuracy', 'precision', 
                           'recall', 'f1_score', 'auc_roc', 'loss']
            for key in history_keys:
                if key in sample:
                    print(f"✓ History record contains: {key}")
                else:
                    print(f"✗ History record missing: {key}")
                    all_ok = False
        
        return all_ok
    
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def main():
    print("=" * 60)
    print("END-TO-END DATA FLOW TEST")
    print("=" * 60)
    
    tests = [
        ('JSON Structure', test_json_structure),
        ('Metrics Loader', test_metrics_loader),
        ('Metric Distinctness', test_metric_distinctness),
        ('Metric Ranges', test_metric_ranges),
        ('Training History', test_training_history),
        ('Template Compatibility', test_template_compatibility),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n✗ Test '{test_name}' crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")
    
    print()
    if passed == total:
        print(f"✓ ALL {total} TESTS PASSED - DATA PIPELINE IS CORRECT")
        return 0
    else:
        print(f"✗ {total - passed} of {total} TESTS FAILED")
        return 1

if __name__ == '__main__':
    exit(main())
