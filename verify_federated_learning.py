#!/usr/bin/env python3
"""
Federated Learning: Implementation Verification Script

This script verifies that all components of the federated learning system
are properly installed and configured.

Usage:
    python verify_federated_learning.py
"""

import os
import json
import sys
from pathlib import Path

def check_file_exists(path, description):
    """Check if a file exists."""
    if os.path.exists(path):
        print(f"✅ {description}: {path}")
        return True
    else:
        print(f"❌ {description}: {path} (NOT FOUND)")
        return False

def check_directory_exists(path, description):
    """Check if a directory exists."""
    if os.path.isdir(path):
        print(f"✅ {description}: {path}")
        return True
    else:
        print(f"⚠️  {description}: {path} (will be created on first submission)")
        return False

def check_json_valid(path, description):
    """Check if JSON file is valid."""
    try:
        with open(path, 'r') as f:
            json.load(f)
        print(f"✅ {description}: {path} (valid JSON)")
        return True
    except FileNotFoundError:
        print(f"❌ {description}: {path} (NOT FOUND)")
        return False
    except json.JSONDecodeError:
        print(f"❌ {description}: {path} (INVALID JSON)")
        return False

def check_python_imports():
    """Check required Python packages."""
    required_packages = {
        'flask': 'Flask',
        'werkzeug': 'Werkzeug',
        'requests': 'Requests',
        'torch': 'PyTorch (optional, for notebook only)'
    }
    
    print("\n" + "="*60)
    print("PYTHON PACKAGES")
    print("="*60)
    
    all_installed = True
    for package_name, package_display in required_packages.items():
        try:
            __import__(package_name)
            print(f"✅ {package_display}")
        except ImportError:
            if 'optional' in package_display:
                print(f"⚠️  {package_display} (optional, needed for notebook)")
            else:
                print(f"❌ {package_display}")
                all_installed = False
    
    return all_installed

def check_code_implementations():
    """Check if key functions are implemented in app.py."""
    print("\n" + "="*60)
    print("KEY FUNCTIONS IN app.py")
    print("="*60)
    
    try:
        with open('app.py', 'r') as f:
            app_content = f.read()
    except FileNotFoundError:
        print("❌ app.py not found")
        return False
    
    required_functions = [
        'load_hospital_tokens',
        'verify_api_key',
        'get_hospital_submissions',
        'is_rate_limited',
        'submit_model_update',
        'def submit_model_update'
    ]
    
    all_present = True
    for func in required_functions:
        if func in app_content:
            print(f"✅ Function '{func}' implemented")
        else:
            print(f"❌ Function '{func}' NOT found")
            all_present = False
    
    # Check for specific constants
    constants = [
        'ALLOWED_WEIGHT_EXTENSIONS',
        'MAX_WEIGHT_FILE_SIZE',
        'INCOMING_MODELS_DIR',
        'CONFIG_DIR'
    ]
    
    print("\nConstants in app.py:")
    for const in constants:
        if const in app_content:
            print(f"✅ Constant '{const}' defined")
        else:
            print(f"❌ Constant '{const}' NOT defined")
            all_present = False
    
    return all_present

def check_notebook_cells():
    """Check if notebook has new federated learning cells."""
    print("\n" + "="*60)
    print("NOTEBOOK CELLS (Medledger_rev2.ipynb)")
    print("="*60)
    
    try:
        with open('Medledger_rev2.ipynb', 'r') as f:
            notebook_content = f.read()
    except FileNotFoundError:
        print("❌ Medledger_rev2.ipynb not found")
        return False
    
    required_cells = [
        ('Step 6', 'torch.save(model.state_dict()'),
        ('Step 7', 'metrics_round'),
        ('Step 8', '/api/submit_update')
    ]
    
    all_present = True
    for cell_name, marker in required_cells:
        if marker in notebook_content:
            print(f"✅ {cell_name}: Found key code")
        else:
            print(f"❌ {cell_name}: NOT found")
            all_present = False
    
    return all_present

def check_api_endpoint():
    """Check if API endpoint is accessible (requires running server)."""
    print("\n" + "="*60)
    print("API ENDPOINT TEST")
    print("="*60)
    
    try:
        import requests
    except ImportError:
        print("⚠️  Requests not installed, skipping endpoint test")
        return None
    
    try:
        response = requests.get('http://localhost:5000', timeout=2)
        print(f"✅ Flask server is running on localhost:5000")
        return True
    except requests.exceptions.ConnectionError:
        print(f"❌ Flask server not running on localhost:5000")
        print("   Run: python app.py")
        return False
    except requests.exceptions.Timeout:
        print(f"⚠️  Flask server connection timed out")
        return False
    except Exception as e:
        print(f"⚠️  Could not test connection: {str(e)}")
        return False

def main():
    """Run all verification checks."""
    print("\n" + "="*60)
    print("FEDERATED LEARNING SYSTEM VERIFICATION")
    print("="*60)
    
    # Check files
    print("\n" + "="*60)
    print("FILES AND DIRECTORIES")
    print("="*60)
    
    files_ok = all([
        check_file_exists('app.py', 'Flask application'),
        check_file_exists('config/hospitals.json', 'Hospital tokens config'),
        check_file_exists('client_test_upload.py', 'Test script'),
        check_file_exists('Medledger_rev2.ipynb', 'Training notebook'),
        check_file_exists('FEDERATED_LEARNING_SETUP.md', 'Setup guide'),
        check_file_exists('QUICKSTART_FEDERATED_LEARNING.md', 'Quick start guide'),
        check_file_exists('FEDERATED_LEARNING_IMPLEMENTATION.md', 'Implementation summary'),
    ])
    
    dirs_ok = all([
        check_directory_exists('config', 'Config directory'),
        check_directory_exists('models', 'Models directory'),
        check_directory_exists('models/incoming', 'Incoming models directory (auto-created)'),
    ])
    
    # Check JSON validity
    print("\n" + "="*60)
    print("CONFIGURATION FILES")
    print("="*60)
    
    json_ok = check_json_valid('config/hospitals.json', 'Hospital tokens config')
    
    # Check Python imports
    imports_ok = check_python_imports()
    
    # Check code implementations
    code_ok = check_code_implementations()
    
    # Check notebook
    notebook_ok = check_notebook_cells()
    
    # Test API endpoint (optional)
    server_ok = check_api_endpoint()
    
    # Summary
    print("\n" + "="*60)
    print("VERIFICATION SUMMARY")
    print("="*60)
    
    results = {
        'Files': files_ok,
        'Directories': dirs_ok,
        'JSON Config': json_ok,
        'Python Imports': imports_ok,
        'Code Implementation': code_ok,
        'Notebook Cells': notebook_ok,
    }
    
    all_ok = all(results.values())
    
    print("\nChecklist:")
    for check, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}: {check}")
    
    if server_ok is not None:
        status = "✅ PASS" if server_ok else "❌ FAIL"
        print(f"  {status}: Flask Server Running (optional)")
    
    if all_ok:
        print("\n" + "="*60)
        print("✅ ALL CHECKS PASSED!")
        print("="*60)
        print("\nNext steps:")
        print("1. Start Flask server: python app.py")
        print("2. Test submission: python client_test_upload.py")
        print("3. View stored model: ls models/incoming/hospital_1/round_1/")
        print("\nFor detailed guide, see:")
        print("  - QUICKSTART_FEDERATED_LEARNING.md")
        print("  - FEDERATED_LEARNING_SETUP.md")
        return 0
    else:
        print("\n" + "="*60)
        print("⚠️  SOME CHECKS FAILED")
        print("="*60)
        print("\nTroubleshooting:")
        if not files_ok:
            print("  - Make sure all required files exist")
            print("  - Check you're in the project root directory")
        if not imports_ok:
            print("  - Install packages: pip install flask werkzeug requests")
        if not json_ok:
            print("  - Create config/hospitals.json with valid JSON")
        print("\nFor help, see FEDERATED_LEARNING_SETUP.md")
        return 1

if __name__ == '__main__':
    sys.exit(main())
