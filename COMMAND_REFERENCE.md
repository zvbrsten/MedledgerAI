# Federated Learning: Command Reference

Quick reference for common commands and operations.

## Server Commands

### Start Flask Server
```bash
python app.py
# Output: Running on http://0.0.0.0:5000
```

### Check Server Status
```bash
curl http://localhost:5000
# Should get a response (check Flask is running)
```

## Testing Commands

### Run Integration Tests (26 tests)
```bash
python test_federated_learning.py
# Expected: ✅ ALL TESTS PASSED
```

### Run Verification Script
```bash
python verify_federated_learning.py
# Checks all components are installed
```

### Quick Test: Submit Model
```bash
# Test with defaults (hospital_1, round 1)
python client_test_upload.py

# Test with specific hospital
python client_test_upload.py --hospital-id hospital_2

# Test with custom metrics
python client_test_upload.py \
  --hospital-id hospital_1 \
  --round 3 \
  --accuracy 0.9054 \
  --loss 0.22

# Test with real weights file
python client_test_upload.py \
  --hospital-id hospital_1 \
  --weights my_model.pt \
  --accuracy 0.8638 \
  --loss 0.36 \
  --no-cleanup
```

## API Testing Commands

### Test Missing API Key
```bash
curl -X POST http://localhost:5000/api/submit_update \
  -F "hospital_id=hospital_1" \
  -F "round=1" \
  -F "weights=@dummy.pt" \
  -F "metrics={\"accuracy\": 0.86, \"loss\": 0.36}"
# Expected: 401 Missing X-API-KEY header
```

### Test Invalid API Key
```bash
curl -X POST http://localhost:5000/api/submit_update \
  -H "X-API-KEY: wrong_key" \
  -F "hospital_id=hospital_1" \
  -F "round=1" \
  -F "weights=@dummy.pt" \
  -F "metrics={\"accuracy\": 0.86, \"loss\": 0.36}"
# Expected: 401 Invalid API key
```

### Test Valid Submission
```bash
curl -X POST http://localhost:5000/api/submit_update \
  -H "X-API-KEY: hospital1_token_abc123def456" \
  -F "hospital_id=hospital_1" \
  -F "round=1" \
  -F "weights=@dummy.pt" \
  -F "metrics={\"accuracy\": 0.86, \"loss\": 0.36}"
# Expected: 200 Model update received successfully
```

### Test File Size Limit
```bash
# Create large file (250 MB)
dd if=/dev/zero of=large_weights.pt bs=1M count=250

# Try to submit (should fail)
curl -X POST http://localhost:5000/api/submit_update \
  -H "X-API-KEY: hospital1_token_abc123def456" \
  -F "hospital_id=hospital_1" \
  -F "round=1" \
  -F "weights=@large_weights.pt" \
  -F "metrics={\"accuracy\": 0.86, \"loss\": 0.36}"
# Expected: 413 File too large
```

## File Management Commands

### View Submitted Models
```bash
# List all hospitals
ls models/incoming/

# List all rounds for hospital_1
ls models/incoming/hospital_1/

# List all files in a submission
ls models/incoming/hospital_1/round_1/
# Output: weights.pt, weights.sha256, metadata.json
```

### View Metadata
```bash
# View as JSON (pretty-printed)
cat models/incoming/hospital_1/round_1/metadata.json | python -m json.tool

# Or with jq if installed
cat models/incoming/hospital_1/round_1/metadata.json | jq .
```

### Check File Hash
```bash
# View stored hash
cat models/incoming/hospital_1/round_1/weights.sha256

# Verify hash matches file
sha256sum models/incoming/hospital_1/round_1/weights.pt
```

### Clean Up Test Files
```bash
# Remove a specific hospital's submissions
rm -rf models/incoming/hospital_1

# Remove all incoming submissions
rm -rf models/incoming

# Remove test weights files
rm -f local_model_test.pt local_model_round*.pt metrics_round*.json
```

## Notebook Commands

### Run Notebook
```bash
jupyter notebook Medledger_rev2.ipynb
```

### Run Specific Cells
In Jupyter, execute cells in this order:
1. Cells 1-5: Training (existing)
2. Cell 18: Export model weights (new)
3. Cell 19: Export training metrics (new)
4. Cell 20: Submit to server (new)

### Extract from Notebook
```python
# Open notebook in Python
import json
with open('Medledger_rev2.ipynb', 'r') as f:
    notebook = json.load(f)

# Print cell count
print(f"Total cells: {len(notebook['cells'])}")

# Find federated learning cells
for i, cell in enumerate(notebook['cells']):
    if 'submit_update' in cell['source']:
        print(f"Cell {i}: Submit endpoint")
    elif 'torch.save' in cell['source']:
        print(f"Cell {i}: Export weights")
    elif 'metrics_round' in cell['source']:
        print(f"Cell {i}: Export metrics")
```

## Configuration Commands

### View Hospital Tokens
```bash
cat config/hospitals.json

# Pretty-print
python -c "import json; print(json.dumps(json.load(open('config/hospitals.json')), indent=2))"
```

### Update Hospital Token
```bash
# Edit config file
cat > config/hospitals.json << 'EOF'
{
  "hospital_1": "new_token_value",
  "hospital_2": "hospital2_token_xyz789uvw012"
}
EOF
```

### Use Environment Variable
```bash
# Set API key as environment variable
export HOSPITAL_API_KEY="hospital1_token_abc123def456"

# In Python, access with:
api_key = os.environ.get('HOSPITAL_API_KEY')
```

## Debugging Commands

### Check Flask Logs
```bash
# Flask outputs to stdout
# Look for:
# - "MODEL UPDATE RECEIVED" - successful submission
# - "AUTH FAILED" - authentication error
# - "Rate limit exceeded" - too many requests
```

### View Request Headers
```bash
# Using curl with verbose output
curl -v -X POST http://localhost:5000/api/submit_update \
  -H "X-API-KEY: hospital1_token_abc123def456" \
  -F "hospital_id=hospital_1" \
  -F "round=1" \
  -F "weights=@dummy.pt" \
  -F "metrics={\"accuracy\": 0.86, \"loss\": 0.36}"
# Look for "X-API-KEY" in request headers
```

### Test Metrics Validation
```python
import json

# Test metrics parsing
metrics_json = '{"accuracy": 0.8638, "loss": 0.36, "num_samples": 100}'
metrics = json.loads(metrics_json)

# Check required fields
required_fields = {'accuracy', 'loss'}
if required_fields.issubset(set(metrics.keys())):
    print("✅ Valid metrics")
else:
    print("❌ Missing required fields")

# Check value ranges
if 0 <= metrics['accuracy'] <= 1 and metrics['loss'] >= 0:
    print("✅ Valid metric values")
else:
    print("❌ Invalid metric values")
```

## Installation/Setup Commands

### Install Dependencies
```bash
pip install flask werkzeug requests torch
```

### Create Config Directory
```bash
mkdir -p config
```

### Create Models Directory
```bash
mkdir -p models/incoming
```

### Initialize (one-time)
```bash
# The app.py creates required directories on startup
python app.py
# Press Ctrl+C to stop
```

## Performance/Monitoring Commands

### Check Submission Success Rate
```bash
# Count successful submissions
find models/incoming -name "metadata.json" | wc -l

# Count hospitals with submissions
ls models/incoming | wc -l

# Calculate average model size
du -sh models/incoming/*/*/weights.pt | awk '{sum+=$1} END {print "Total:", sum}'
```

### List Recent Submissions
```bash
# Most recent submissions
find models/incoming -name "metadata.json" | xargs ls -lt | head -10
```

### Check Rate Limiting (in-memory)
```python
# Rate limiting is tracked in app.request_times
# Cannot check directly without accessing app instance
# But can infer from request patterns:

import os
import json
from datetime import datetime

# Count submissions in last minute
recent = []
for root, dirs, files in os.walk('models/incoming'):
    if 'metadata.json' in files:
        metadata_path = os.path.join(root, 'metadata.json')
        with open(metadata_path) as f:
            metadata = json.load(f)
            received = datetime.fromisoformat(metadata['received_at'].replace('Z', '+00:00'))
            if (datetime.now(received.tzinfo) - received).total_seconds() < 60:
                recent.append(metadata)

print(f"Submissions in last minute: {len(recent)}")
if len(recent) >= 10:
    print("⚠️  Rate limit will be active for new submissions")
```

## Network Troubleshooting

### Test Network Connectivity
```bash
# Test if server is reachable
ping localhost
ping 127.0.0.1
ping 0.0.0.0  # May not work depending on network config

# Test port availability
netstat -tulpn | grep 5000
# Or on Windows:
netstat -ano | findstr :5000
```

### Check Port in Use
```bash
# On macOS/Linux
lsof -i :5000

# On Windows
netstat -ano | findstr :5000
taskkill /PID <PID> /F  # Kill process if needed
```

### Test Connectivity from Different Host
```bash
# From another computer on network
curl http://<server-ip>:5000

# From same network
curl http://192.168.1.100:5000  # Replace with actual IP
```

## Documentation Commands

### View Documentation
```bash
# View setup guide
cat FEDERATED_LEARNING_SETUP.md | less

# Search documentation
grep -r "rate limit" FEDERATED_LEARNING*.md

# View implementation details
cat FEDERATED_LEARNING_IMPLEMENTATION.md
```

### Generate Documentation Index
```bash
# List all markdown files
ls -1 *.md | sort

# Count documentation files
ls -1 *.md | wc -l

# Show file sizes
ls -lh *.md | grep FEDERATED
```

## One-Liner Tests

```bash
# Quick test: start server, test submission, view result (3 commands)
python app.py &  # Start in background
sleep 2  # Wait for server
python client_test_upload.py  # Test submission
kill %1  # Kill server

# View all submissions
find models/incoming -type f -name "*.json" | xargs ls -l

# Count total submissions
find models/incoming -name "metadata.json" -exec wc -l {} + | tail -1

# Check if hospital has submitted
ls models/incoming | grep hospital_1

# View latest submission
ls -lt models/incoming/hospital_1/*/metadata.json | head -1 | xargs cat
```

## CI/CD Integration

```bash
# Run all tests (CI pipeline)
python test_federated_learning.py && \
python verify_federated_learning.py && \
echo "✅ All tests passed"

# Check code quality
python -m py_compile app.py client_test_upload.py test_federated_learning.py

# Check syntax
python -m flake8 app.py --count --select=E9,F63,F7,F82 --show-source
```

---

For more detailed information, see:
- [QUICKSTART_FEDERATED_LEARNING.md](QUICKSTART_FEDERATED_LEARNING.md) - 5-minute guide
- [FEDERATED_LEARNING_SETUP.md](FEDERATED_LEARNING_SETUP.md) - Complete setup guide
- [FEDERATED_LEARNING_IMPLEMENTATION.md](FEDERATED_LEARNING_IMPLEMENTATION.md) - Implementation details
