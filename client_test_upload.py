#!/usr/bin/env python3
"""
Federated Learning: Client-Side Test Upload
=============================================

This script demonstrates how a hospital would submit a local model update
to the central coordination server via the /api/submit_update endpoint.

SECURITY NOTE:
- This script runs on the HOSPITAL MACHINE
- The weights file never contains patient data
- Only the trained model weights and summary metrics are sent
- Authentication uses pre-shared API key (X-API-KEY header)

Usage:
    python client_test_upload.py --hospital-id hospital_1 \
                                  --api-key YOUR_TOKEN \
                                  --server-url http://localhost:5000 \
                                  --round 1 \
                                  --weights local_model_round1.pt \
                                  --accuracy 0.8638 \
                                  --loss 0.36
"""

import os
import json
import argparse
import hashlib
import requests
from pathlib import Path
from datetime import datetime


def create_dummy_weights(output_path='local_model_test.pt'):
    """
    Create a small dummy .pt file for testing (simulates PyTorch weights).
    In real usage, this would be the actual model state dict from training.
    """
    # Create a minimal PyTorch-like weight file (just binary data for this test)
    dummy_content = b'PYTORCH_TEST_WEIGHTS_' + os.urandom(1024)
    with open(output_path, 'wb') as f:
        f.write(dummy_content)
    return output_path


def compute_file_hash(filepath):
    """Compute SHA-256 hash of file for verification."""
    sha256 = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


def submit_model_update(
    server_url,
    hospital_id,
    api_key,
    round_num,
    weights_path,
    accuracy,
    loss,
    num_samples=None,
    verbose=True
):
    """
    Submit model update to central server.
    
    Args:
        server_url: Base URL of coordination server (e.g., http://localhost:5000)
        hospital_id: Hospital identifier (e.g., hospital_1)
        api_key: Pre-shared API token
        round_num: Training round number
        weights_path: Path to .pt weights file
        accuracy: Model accuracy (0-1)
        loss: Training loss
        num_samples: Number of training samples (optional)
        verbose: Print progress
    
    Returns:
        dict with 'success', 'message', 'response_code'
    """
    
    endpoint = f'{server_url}/api/submit_update'
    
    if verbose:
        print(f'\n{"="*60}')
        print('FEDERATED LEARNING: Model Update Submission')
        print(f'{"="*60}')
        print(f'Hospital ID:   {hospital_id}')
        print(f'Round:         {round_num}')
        print(f'Accuracy:      {accuracy:.4f}')
        print(f'Loss:          {loss:.4f}')
        print(f'Weights file:  {weights_path}')
        print(f'File size:     {os.path.getsize(weights_path) / (1024*1024):.2f} MB')
        print(f'Hash (SHA256): {compute_file_hash(weights_path)[:16]}...')
        print(f'Endpoint:      {endpoint}')
        print(f'{"="*60}')
    
    # Validate file exists
    if not os.path.exists(weights_path):
        return {
            'success': False,
            'message': f'Weights file not found: {weights_path}',
            'response_code': None
        }
    
    # Prepare metrics JSON
    metrics = {
        'accuracy': float(accuracy),
        'loss': float(loss),
        'num_samples': num_samples or 100,
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    }
    
    # Prepare multipart form
    files = {
        'weights': open(weights_path, 'rb')
    }
    
    data = {
        'hospital_id': hospital_id,
        'round': round_num,
        'metrics': json.dumps(metrics)
    }
    
    headers = {
        'X-API-KEY': api_key
    }
    
    if verbose:
        print('\nSubmitting model update...')
    
    try:
        response = requests.post(
            endpoint,
            files=files,
            data=data,
            headers=headers,
            timeout=30
        )
        
        files['weights'].close()
        
        response_json = response.json() if response.text else {}
        
        if verbose:
            print(f'\nResponse Code:  {response.status_code}')
            print(f'Response:       {json.dumps(response_json, indent=2)}')
        
        success = response.status_code == 200
        
        if success:
            print('\n✓ Model update submitted successfully!')
            print(f'  Submission ID: {response_json.get("metadata_id", "N/A")}')
        else:
            print(f'\n✗ Submission failed ({response.status_code}):')
            print(f'  {response_json.get("error", "Unknown error")}')
        
        return {
            'success': success,
            'message': response_json.get('message') or response_json.get('error', ''),
            'response_code': response.status_code,
            'response': response_json
        }
    
    except requests.exceptions.ConnectionError as e:
        return {
            'success': False,
            'message': f'Connection error: {str(e)}',
            'response_code': None
        }
    
    except requests.exceptions.Timeout:
        return {
            'success': False,
            'message': 'Request timeout. Server may be unresponsive.',
            'response_code': None
        }
    
    except Exception as e:
        return {
            'success': False,
            'message': f'Error: {str(e)}',
            'response_code': None
        }


def main():
    parser = argparse.ArgumentParser(
        description='Submit model update to federated learning coordination server'
    )
    parser.add_argument(
        '--server-url',
        default='http://localhost:5000',
        help='Server URL (default: http://localhost:5000)'
    )
    parser.add_argument(
        '--hospital-id',
        default='hospital_1',
        help='Hospital identifier (default: hospital_1)'
    )
    parser.add_argument(
        '--api-key',
        required=False,
        help='API key for authentication (will prompt if not provided)'
    )
    parser.add_argument(
        '--round',
        type=int,
        default=1,
        help='Training round number (default: 1)'
    )
    parser.add_argument(
        '--weights',
        help='Path to .pt weights file (creates dummy if not specified)'
    )
    parser.add_argument(
        '--accuracy',
        type=float,
        default=0.8638,
        help='Model accuracy (default: 0.8638)'
    )
    parser.add_argument(
        '--loss',
        type=float,
        default=0.36,
        help='Training loss (default: 0.36)'
    )
    parser.add_argument(
        '--num-samples',
        type=int,
        help='Number of training samples'
    )
    parser.add_argument(
        '--no-cleanup',
        action='store_true',
        help='Do not delete test weights file after submission'
    )
    
    args = parser.parse_args()
    
    # Get API key
    if not args.api_key:
        # Try to load from config
        config_path = 'config/hospitals.json'
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = json.load(f)
                args.api_key = config.get(args.hospital_id)
                if args.api_key:
                    print(f'✓ Loaded API key for {args.hospital_id} from {config_path}')
                else:
                    print(f'✗ Hospital {args.hospital_id} not found in {config_path}')
                    return
        else:
            print(f'✗ config/hospitals.json not found')
            return
    
    # Get weights file
    if not args.weights:
        print('Creating dummy weights file for testing...')
        args.weights = create_dummy_weights()
    
    # Submit
    result = submit_model_update(
        server_url=args.server_url,
        hospital_id=args.hospital_id,
        api_key=args.api_key,
        round_num=args.round,
        weights_path=args.weights,
        accuracy=args.accuracy,
        loss=args.loss,
        num_samples=args.num_samples,
        verbose=True
    )
    
    # Cleanup
    if not args.no_cleanup and 'local_model_test' in args.weights:
        try:
            os.remove(args.weights)
            print(f'\nCleaned up test file: {args.weights}')
        except:
            pass
    
    return 0 if result['success'] else 1


if __name__ == '__main__':
    exit(main())
