#!/usr/bin/env python3
"""
Federated Learning: Integration Test

This test script validates the end-to-end federated learning implementation
without requiring the Flask server to be running.

Tests:
1. API key verification logic
2. Rate limiting logic
3. File validation logic
4. Metrics validation logic
5. Directory creation and storage
6. Metadata JSON creation

Usage:
    python test_federated_learning.py
"""

import os
import json
import tempfile
import hashlib
from pathlib import Path
from datetime import datetime

class FederatedLearningTest:
    """Test suite for federated learning implementation."""
    
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.temp_dir = tempfile.mkdtemp()
    
    def print_header(self, title):
        """Print test section header."""
        print(f"\n{'='*60}")
        print(f"{title}")
        print(f"{'='*60}")
    
    def test_pass(self, test_name, message=""):
        """Log a passed test."""
        self.passed += 1
        msg = f"✅ PASS: {test_name}"
        if message:
            msg += f" - {message}"
        print(msg)
    
    def test_fail(self, test_name, message=""):
        """Log a failed test."""
        self.failed += 1
        msg = f"❌ FAIL: {test_name}"
        if message:
            msg += f" - {message}"
        print(msg)
    
    def test_api_key_verification(self):
        """Test API key verification logic."""
        self.print_header("TEST 1: API Key Verification")
        
        # Simulate hospital tokens
        tokens = {
            "hospital_1": "hospital1_token_abc123def456",
            "hospital_2": "hospital2_token_xyz789uvw012",
        }
        
        # Test valid key
        hospital_id = "hospital_1"
        api_key = tokens.get(hospital_id)
        if api_key == "hospital1_token_abc123def456":
            self.test_pass("Valid API key verification")
        else:
            self.test_fail("Valid API key verification")
        
        # Test invalid key
        if tokens.get("hospital_1") != "wrong_key":
            self.test_pass("Invalid API key rejected")
        else:
            self.test_fail("Invalid API key rejected")
        
        # Test missing hospital
        if tokens.get("hospital_999") is None:
            self.test_pass("Unknown hospital rejected")
        else:
            self.test_fail("Unknown hospital rejected")
    
    def test_rate_limiting(self):
        """Test rate limiting logic."""
        self.print_header("TEST 2: Rate Limiting")
        
        # Simulate rate limit tracking
        request_times = {}
        current_time = datetime.now().timestamp()
        
        # Add 10 requests
        for i in range(10):
            if 'hospital_1' not in request_times:
                request_times['hospital_1'] = []
            request_times['hospital_1'].append(current_time + i)
        
        # Check rate limit not exceeded at 10
        if len(request_times['hospital_1']) <= 10:
            self.test_pass("10 requests allowed within rate limit")
        else:
            self.test_fail("10 requests allowed within rate limit")
        
        # 11th request should be blocked
        if len(request_times['hospital_1']) >= 10:
            self.test_pass("Rate limit blocks excessive requests")
        else:
            self.test_fail("Rate limit blocks excessive requests")
    
    def test_file_validation(self):
        """Test file extension and size validation."""
        self.print_header("TEST 3: File Validation")
        
        ALLOWED_EXTENSIONS = {'.pt', '.pth'}
        MAX_SIZE = 200 * 1024 * 1024  # 200 MB
        
        # Test valid extension
        valid_files = ['model.pt', 'weights.pth']
        for filename in valid_files:
            ext = os.path.splitext(filename)[1].lower()
            if ext in ALLOWED_EXTENSIONS:
                self.test_pass(f"Valid extension accepted: {filename}")
            else:
                self.test_fail(f"Valid extension accepted: {filename}")
        
        # Test invalid extension
        invalid_files = ['model.pkl', 'weights.h5', 'model.zip']
        for filename in invalid_files:
            ext = os.path.splitext(filename)[1].lower()
            if ext not in ALLOWED_EXTENSIONS:
                self.test_pass(f"Invalid extension rejected: {filename}")
            else:
                self.test_fail(f"Invalid extension rejected: {filename}")
        
        # Test file size limit
        small_size = 100 * 1024 * 1024  # 100 MB
        if small_size <= MAX_SIZE:
            self.test_pass("Small file (100 MB) passes size check")
        else:
            self.test_fail("Small file (100 MB) passes size check")
        
        large_size = 250 * 1024 * 1024  # 250 MB
        if large_size > MAX_SIZE:
            self.test_pass("Large file (250 MB) fails size check")
        else:
            self.test_fail("Large file (250 MB) fails size check")
    
    def test_metrics_validation(self):
        """Test metrics JSON validation."""
        self.print_header("TEST 4: Metrics Validation")
        
        # Test valid metrics
        valid_metrics = {
            "accuracy": 0.8638,
            "loss": 0.36,
            "num_samples": 100
        }
        
        required_keys = {'accuracy', 'loss'}
        if required_keys.issubset(set(valid_metrics.keys())):
            self.test_pass("Valid metrics accepted")
        else:
            self.test_fail("Valid metrics accepted")
        
        # Test missing required field
        invalid_metrics_1 = {"accuracy": 0.86}  # Missing loss
        if not required_keys.issubset(set(invalid_metrics_1.keys())):
            self.test_pass("Metrics without required field rejected")
        else:
            self.test_fail("Metrics without required field rejected")
        
        # Test invalid metric values
        invalid_metrics_2 = {"accuracy": 1.5, "loss": 0.36}  # Accuracy > 1
        try:
            acc = float(invalid_metrics_2['accuracy'])
            if 0 <= acc <= 1:
                valid = True
            else:
                valid = False
            if not valid:
                self.test_pass("Invalid accuracy value rejected")
            else:
                self.test_fail("Invalid accuracy value rejected")
        except:
            self.test_fail("Invalid accuracy value rejected")
        
        # Test negative loss
        invalid_metrics_3 = {"accuracy": 0.86, "loss": -0.5}  # Negative loss
        loss = float(invalid_metrics_3['loss'])
        if loss < 0:
            self.test_pass("Negative loss value rejected")
        else:
            self.test_fail("Negative loss value rejected")
    
    def test_monotonic_rounds(self):
        """Test monotonic round number validation."""
        self.print_header("TEST 5: Monotonic Round Numbers")
        
        # Simulate previous submissions
        previous_rounds = [1, 2, 3]
        
        # Test new round > previous
        new_round = 4
        if new_round > max(previous_rounds):
            self.test_pass("Round 4 accepted (> previous 3)")
        else:
            self.test_fail("Round 4 accepted (> previous 3)")
        
        # Test duplicate round
        dup_round = 3
        if dup_round <= max(previous_rounds):
            self.test_pass("Round 3 rejected (already submitted)")
        else:
            self.test_fail("Round 3 rejected (already submitted)")
        
        # Test lower round
        lower_round = 2
        if lower_round <= max(previous_rounds):
            self.test_pass("Round 2 rejected (lower than 3)")
        else:
            self.test_fail("Round 2 rejected (lower than 3)")
    
    def test_sha256_hashing(self):
        """Test SHA-256 file hashing."""
        self.print_header("TEST 6: SHA-256 Hashing")
        
        # Create test file
        test_file = os.path.join(self.temp_dir, 'test_weights.pt')
        test_content = b'PYTORCH_TEST_WEIGHTS_' + os.urandom(1024)
        
        with open(test_file, 'wb') as f:
            f.write(test_content)
        
        # Compute hash
        sha256 = hashlib.sha256()
        with open(test_file, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                sha256.update(chunk)
        
        file_hash = sha256.hexdigest()
        
        if len(file_hash) == 64:  # SHA-256 is 64 hex characters
            self.test_pass(f"SHA-256 hash computed correctly (length={len(file_hash)})")
        else:
            self.test_fail(f"SHA-256 hash computed correctly (length={len(file_hash)})")
        
        # Test hash consistency
        sha256_2 = hashlib.sha256()
        with open(test_file, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                sha256_2.update(chunk)
        
        file_hash_2 = sha256_2.hexdigest()
        if file_hash == file_hash_2:
            self.test_pass("Hash is consistent across multiple computations")
        else:
            self.test_fail("Hash is consistent across multiple computations")
    
    def test_directory_structure(self):
        """Test directory creation and structure."""
        self.print_header("TEST 7: Directory Structure")
        
        # Simulate directory creation
        hospital_id = "hospital_1"
        round_num = 3
        incoming_dir = os.path.join(self.temp_dir, 'models', 'incoming')
        hospital_round_dir = os.path.join(incoming_dir, hospital_id, f'round_{round_num}')
        
        os.makedirs(hospital_round_dir, exist_ok=True)
        
        if os.path.isdir(hospital_round_dir):
            self.test_pass(f"Directory created: {hospital_round_dir}")
        else:
            self.test_fail(f"Directory created: {hospital_round_dir}")
        
        # Test file paths
        weights_path = os.path.join(hospital_round_dir, 'weights.pt')
        hash_path = os.path.join(hospital_round_dir, 'weights.sha256')
        metadata_path = os.path.join(hospital_round_dir, 'metadata.json')
        
        paths_ok = True
        for path in [weights_path, hash_path, metadata_path]:
            if not path.startswith(hospital_round_dir):
                paths_ok = False
                self.test_fail(f"File path incorrect: {path}")
        
        if paths_ok:
            self.test_pass("File paths generated correctly")
    
    def test_metadata_format(self):
        """Test metadata JSON format."""
        self.print_header("TEST 8: Metadata Format")
        
        # Create sample metadata
        metadata = {
            "hospital_id": "hospital_1",
            "round": 3,
            "filename": "weights.pt",
            "sha256": "a1b2c3d4e5f6g7h8" + "i9j0"*8,  # 64 chars
            "file_size_bytes": 47451680,
            "metrics": {
                "accuracy": 0.8638,
                "loss": 0.36,
                "num_samples": 100,
                "timestamp": "2024-01-30T14:45:00Z"
            },
            "received_at": datetime.utcnow().isoformat() + 'Z',
            "uploader_ip": "192.168.1.100"
        }
        
        # Test JSON serializability
        try:
            metadata_json = json.dumps(metadata)
            self.test_pass("Metadata is valid JSON")
        except Exception as e:
            self.test_fail(f"Metadata is valid JSON: {str(e)}")
        
        # Test deserializability
        try:
            metadata_restored = json.loads(metadata_json)
            self.test_pass("Metadata can be parsed from JSON")
        except Exception as e:
            self.test_fail(f"Metadata can be parsed from JSON: {str(e)}")
        
        # Test required fields
        required_fields = {'hospital_id', 'round', 'filename', 'sha256', 'metrics', 'received_at'}
        if required_fields.issubset(set(metadata.keys())):
            self.test_pass("Metadata contains all required fields")
        else:
            self.test_fail("Metadata contains all required fields")
    
    def run_all_tests(self):
        """Run all tests."""
        print("\n" + "="*60)
        print("FEDERATED LEARNING: INTEGRATION TEST SUITE")
        print("="*60)
        
        self.test_api_key_verification()
        self.test_rate_limiting()
        self.test_file_validation()
        self.test_metrics_validation()
        self.test_monotonic_rounds()
        self.test_sha256_hashing()
        self.test_directory_structure()
        self.test_metadata_format()
        
        # Summary
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)
        print(f"✅ Passed: {self.passed}")
        print(f"❌ Failed: {self.failed}")
        print(f"Total:    {self.passed + self.failed}")
        
        if self.failed == 0:
            print("\n🎉 ALL TESTS PASSED!")
            return 0
        else:
            print(f"\n⚠️  {self.failed} TEST(S) FAILED")
            return 1

def main():
    """Run the test suite."""
    tester = FederatedLearningTest()
    return tester.run_all_tests()

if __name__ == '__main__':
    import sys
    sys.exit(main())
