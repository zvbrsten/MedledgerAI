#!/usr/bin/env python3
"""
COMPREHENSIVE SITE VALIDATION REPORT
=====================================
Checks all critical areas for data quality and display issues
"""

import os
import json
import hashlib
from pathlib import Path

def validate_metrics_data():
    """Validate that metrics data has realistic, distinct values"""
    try:
        with open('data/federated_metrics.json', 'r') as f:
            data = json.load(f)
        
        issues = []
        
        # Check 1: Verify all metric arrays exist
        required_arrays = ['accuracy_per_round', 'precision_per_round', 'recall_per_round', 
                          'f1_score_per_round', 'auc_roc_per_round', 'loss_per_round']
        
        for arr in required_arrays:
            if arr not in data:
                issues.append(f"Missing array: {arr}")
            elif len(data[arr]) != 5:
                issues.append(f"Array {arr} has {len(data[arr])} values, expected 5")
        
        # Check 2: Verify metrics are distinct
        acc = data.get('accuracy_per_round', [])
        prec = data.get('precision_per_round', [])
        recall = data.get('recall_per_round', [])
        f1 = data.get('f1_score_per_round', [])
        auc = data.get('auc_roc_per_round', [])
        
        if acc == prec:
            issues.append("ERROR: Precision equals Accuracy")
        if acc == recall:
            issues.append("ERROR: Recall equals Accuracy")
        if acc == f1:
            issues.append("ERROR: F1 Score equals Accuracy")
        if acc == auc:
            issues.append("ERROR: AUC-ROC equals Accuracy")
        
        # Check 3: Verify training history
        history = data.get('training_history', [])
        if len(history) != 5:
            issues.append(f"Training history has {len(history)} records, expected 5")
        
        for i, h in enumerate(history):
            required_keys = ['accuracy', 'precision', 'recall', 'f1_score', 'auc_roc', 'loss']
            for key in required_keys:
                if key not in h:
                    issues.append(f"Round {i+1}: Missing key {key}")
            
            if h.get('accuracy') == h.get('precision'):
                issues.append(f"Round {i+1}: Precision equals Accuracy")
        
        # Check 4: Verify final values are set
        final_keys = ['final_accuracy', 'final_precision', 'final_recall', 'final_auc_roc']
        for key in final_keys:
            if key not in data or data[key] == 0:
                issues.append(f"Missing or zero final value: {key}")
        
        return len(issues) == 0, issues, data
    
    except Exception as e:
        return False, [str(e)], None

def validate_config():
    """Validate hospital configuration"""
    try:
        with open('config/hospitals.json', 'r') as f:
            config = json.load(f)
        
        issues = []
        
        # Check that we have 5 hospitals
        if len(config) != 5:
            issues.append(f"Expected 5 hospitals, found {len(config)}")
        
        # Check that all hospitals have tokens
        for hospital_id, token in config.items():
            if not token or len(token) < 10:
                issues.append(f"Invalid token for {hospital_id}")
        
        return len(issues) == 0, issues
    
    except Exception as e:
        return False, [str(e)]

def validate_templates():
    """Validate HTML templates exist and contain metrics references"""
    issues = []
    
    # Check template files exist
    templates = {
        'templates/model_status.html': ['precision', 'recall', 'auc_roc'],
        'templates/federated_metrics.html': ['accuracy'],
        'templates/admin.html': ['accuracy'],
    }
    
    for template_path, required_strings in templates.items():
        if not os.path.exists(template_path):
            issues.append(f"Missing template: {template_path}")
        else:
            with open(template_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                for required_string in required_strings:
                    if required_string not in content.lower():
                        issues.append(f"Template {template_path} missing reference to {required_string}")
    
    return len(issues) == 0, issues

def validate_python_files():
    """Validate Python files are syntactically correct"""
    issues = []
    
    python_files = [
        'app.py',
        'metrics_loader.py',
        'append_metrics_round.py',
    ]
    
    for py_file in python_files:
        if not os.path.exists(py_file):
            issues.append(f"Missing Python file: {py_file}")
        else:
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    compile(f.read(), py_file, 'exec')
            except SyntaxError as e:
                issues.append(f"Syntax error in {py_file}: {e}")
    
    return len(issues) == 0, issues

def validate_directories():
    """Validate required directories exist"""
    issues = []
    
    required_dirs = [
        'data',
        'templates',
        'static',
        'config',
        'models',
        'models/incoming',
    ]
    
    for dir_path in required_dirs:
        if not os.path.isdir(dir_path):
            issues.append(f"Missing directory: {dir_path}")
    
    return len(issues) == 0, issues

def main():
    print("=" * 70)
    print("COMPREHENSIVE SITE VALIDATION REPORT")
    print("=" * 70)
    print()
    
    # Test 1: Metrics Data
    print("1. METRICS DATA VALIDATION")
    print("-" * 70)
    metrics_ok, metrics_issues, metrics_data = validate_metrics_data()
    if metrics_ok:
        print("✓ All metrics data validation passed")
        if metrics_data:
            print(f"  - Accuracy range: {min(metrics_data['accuracy_per_round']):.4f} to {max(metrics_data['accuracy_per_round']):.4f}")
            print(f"  - Precision range: {min(metrics_data['precision_per_round']):.4f} to {max(metrics_data['precision_per_round']):.4f}")
            print(f"  - Recall range: {min(metrics_data['recall_per_round']):.4f} to {max(metrics_data['recall_per_round']):.4f}")
            print(f"  - AUC-ROC range: {min(metrics_data['auc_roc_per_round']):.4f} to {max(metrics_data['auc_roc_per_round']):.4f}")
            print(f"  - Training history records: {len(metrics_data['training_history'])}")
    else:
        print("✗ Metrics data validation FAILED:")
        for issue in metrics_issues:
            print(f"  - {issue}")
    print()
    
    # Test 2: Configuration
    print("2. CONFIGURATION VALIDATION")
    print("-" * 70)
    config_ok, config_issues = validate_config()
    if config_ok:
        print("✓ Hospital configuration is valid")
        print(f"  - 5 hospitals configured with API tokens")
    else:
        print("✗ Configuration validation FAILED:")
        for issue in config_issues:
            print(f"  - {issue}")
    print()
    
    # Test 3: Templates
    print("3. HTML TEMPLATES VALIDATION")
    print("-" * 70)
    templates_ok, templates_issues = validate_templates()
    if templates_ok:
        print("✓ All HTML templates are valid")
        print(f"  - model_status.html: OK (contains metrics)")
        print(f"  - federated_metrics.html: OK")
        print(f"  - admin.html: OK")
    else:
        print("✗ Template validation FAILED:")
        for issue in templates_issues:
            print(f"  - {issue}")
    print()
    
    # Test 4: Python Files
    print("4. PYTHON FILES VALIDATION")
    print("-" * 70)
    python_ok, python_issues = validate_python_files()
    if python_ok:
        print("✓ All Python files are syntactically correct")
    else:
        print("✗ Python file validation FAILED:")
        for issue in python_issues:
            print(f"  - {issue}")
    print()
    
    # Test 5: Directories
    print("5. DIRECTORY STRUCTURE VALIDATION")
    print("-" * 70)
    dirs_ok, dirs_issues = validate_directories()
    if dirs_ok:
        print("✓ All required directories exist")
    else:
        print("✗ Directory validation FAILED:")
        for issue in dirs_issues:
            print(f"  - {issue}")
    print()
    
    # Summary
    print("=" * 70)
    all_ok = metrics_ok and config_ok and templates_ok and python_ok and dirs_ok
    if all_ok:
        print("✓ ALL VALIDATIONS PASSED - SITE IS READY FOR USE")
    else:
        print("✗ SOME VALIDATIONS FAILED - PLEASE REVIEW ABOVE")
    print("=" * 70)
    
    return 0 if all_ok else 1

if __name__ == '__main__':
    exit(main())
