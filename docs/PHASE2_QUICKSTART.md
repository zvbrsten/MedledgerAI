# Phase 2 Quick Start Guide

## Quick Start (5 minutes)

### 1. Start the Flask Server

```bash
# Terminal 1
cd c:\Medledeger
python app.py
```

Expected output:
```
 * Running on http://0.0.0.0:5000
```

### 2. Test Automatic Aggregation

In a separate terminal, run the comprehensive test:

```bash
# Terminal 2
cd c:\Medledeger
python test_phase2_workflow.py
```

This test:
- Creates mock hospital submissions (Rounds 1-2)
- Automatically triggers aggregation
- Verifies global model is created
- Shows website can access round status

### 3. View Coordination Status on Website

Open browser:
```
http://localhost:5000/model-status
```

You'll see:
```
⚙️ Federated Learning Coordination Status

Current Round: 1
Hospital Submissions: 2 / 5
Aggregation Status: Pending

Hospital Status:
✓ hospital_1 (submitted)
✓ hospital_2 (submitted)
⧗ hospital_3 (waiting)
⧗ hospital_4 (waiting)
⧗ hospital_5 (waiting)
```

(Status updates every 5 seconds)

## Detailed Walkthrough

### Understanding the Flow

1. **Hospital Trains** (on its own data)
   ```python
   # In hospital notebook (Medledger_rev2.ipynb)
   local_model.train()  # Train for LOCAL_EPOCHS
   ```

2. **Hospital Submits** (weights only)
   ```python
   # POST /api/submit_update
   requests.post(
       f"{SERVER_URL}/api/submit_update",
       files={"weights": open("local_model_round1.pt", "rb")},
       data={"hospital_id": "hospital_1", "round": 1}
   )
   ```

3. **Server Registers** (with RoundManager)
   ```python
   # In app.py submit_model_update()
   rm = get_round_manager()
   submission_status = rm.register_submission(
       hospital_id="hospital_1",
       weights_path="models/incoming/hospital_1/round_1/weights.pt",
       num_samples=500
   )
   # Returns: {"ready_for_aggregation": false} (1/5 hospitals)
   ```

4. **Hospital 2-5 Submit** (same process)
   - Server still waiting...
   - RoundManager status: 2/5, 3/5, 4/5

5. **Hospital 5 Submits** (triggers aggregation!)
   ```python
   # Server detects: ALL 5 hospitals submitted
   # Automatically calls:
   aggregator = FedAvgAggregator()
   success, msg, metadata = aggregator.aggregate(submissions, round_num=1)
   # Creates: models/global/global_model_round1.pt
   # Increments: current_round = 2
   ```

6. **Hospitals Download** (aggregated model)
   ```python
   # In next round's notebook execution
   response = requests.get("http://server:5000/api/global-model/latest")
   # Downloads: global_model_round1.pt
   # Uses as starting point for round 2 training
   ```

7. **Website Shows Status** (passive observation)
   ```html
   <!-- /model-status page -->
   Current Round: 2
   Hospital Submissions: 0 / 5 (reset for new round)
   Aggregation Status: ✓ Complete
   ```

### Simulating Hospital Submissions

To manually test without the full notebook:

```python
import requests
import json

# Configure
SERVER = "http://localhost:5000"
HOSPITAL_ID = "hospital_test"
API_KEY = "test_token"

# Create mock weights file
with open("test_weights.pt", "wb") as f:
    f.write(b"mock weights data")

# Submit
response = requests.post(
    f"{SERVER}/api/submit_update",
    files={"weights": open("test_weights.pt", "rb")},
    data={
        "hospital_id": HOSPITAL_ID,
        "round": 1,
        "metrics": json.dumps({"accuracy": 0.92, "loss": 0.15, "num_samples": 500})
    },
    headers={"X-API-KEY": API_KEY}
)

print(response.json())
# {
#   "success": true,
#   "aggregation_status": "registered" or "round_complete"
# }
```

### Checking Round Status

```python
import requests

response = requests.get("http://localhost:5000/api/round-status")
status = response.json()

print(f"Round: {status['current_round']}")
print(f"Submissions: {status['received_hospitals']}")
print(f"Missing: {status['missing_hospitals']}")
print(f"Ready: {status['ready_for_aggregation']}")
```

### Downloading Aggregated Model

```python
import requests

response = requests.get("http://localhost:5000/api/global-model/latest")

# Check headers for metadata
round_num = response.headers['X-GLOBAL-ROUND']
model_hash = response.headers['X-MODEL-HASH']

# Save model
with open(f"global_model_round{round_num}.pt", "wb") as f:
    f.write(response.content)

print(f"Downloaded round {round_num} model")
```

## File Locations

### Round State

```
data/round_state.json
```

Shows current round, submitted hospitals, aggregation status.

### Hospital Submissions

```
models/incoming/
├── hospital_1/
│   └── round_1/
│       ├── weights.pt         (sent by hospital)
│       ├── metadata.json      (server-generated)
│       └── weights.sha256     (tamper detection)
├── hospital_2/...
└── hospital_5/...
```

### Aggregated Models

```
models/global/
├── global_model_round1.pt     (result of FedAvg for round 1)
├── global_model_round2.pt     (result of FedAvg for round 2)
└── global_model_round3.pt     (result of FedAvg for round 3)
```

These are downloaded by hospitals for next round training.

## Architecture Guarantees

### ✓ Security

```
Hospital Data STAYS LOCAL
        ↓
Hospitals compute metrics LOCALLY
        ↓
Only weights sent to server (NO data)
        ↓
Server computes FedAvg (pure math)
        ↓
Global model sent back to hospitals (NO data)
        ↓
Hospital continues with next round (with data)
```

### ✓ Privacy

- Hospital 1's data: only seen by Hospital 1
- Hospital 2's data: only seen by Hospital 2
- Server: sees ONLY weights (model parameters)
- Website: sees ONLY metrics and round status

### ✓ Determinism

- Same hospitals with same data → same aggregated model
- Idempotent: running aggregation twice = same result
- No race conditions (round manager ensures serialization)

### ✓ Auditability

```
data/round_state.json: Which round, who submitted
models/incoming/.../metadata.json: When submitted, accuracy
models/global/global_model_roundN.pt: Aggregated result
app.py logs: All submissions, all aggregations
```

## Troubleshooting

### "ModuleNotFoundError: No module named 'torch'"

**Expected in test environment.** The aggregation will:
1. Try real aggregation (requires torch)
2. Fall back to mock file creation (for testing)

In production with PyTorch installed, real FedAvg happens.

### "Cannot connect to http://localhost:5000"

Make sure Flask server is running:
```bash
python app.py
```

### "404 No global model available yet"

This is normal! It means:
- No aggregation has completed
- Hospitals haven't submitted for round 1 yet
- Try submitting from all 5 hospitals first

### "HTTP 401 Invalid API key"

The hospital API key doesn't match. Check:
```json
config/hospitals.json
{
  "hospital_1": "hospital1_token_abc123",
  "hospital_2": "hospital2_token_def456",
  ...
}
```

## Next Steps

### For Hospitals

1. **Update notebook to download global model**
   - Cell 2 already added (automatic)
   - Downloads from `/api/global-model/latest`
   - Uses as starting point for round N+1

2. **Configure submission to server**
   ```python
   SERVER_URL = "http://your-server:5000"
   API_KEY = "your-hospital-token"
   ```

3. **Run complete training loop**
   - Round 1: train from base, submit
   - Server aggregates
   - Round 2: download aggregated model, train, submit
   - Repeat...

### For Server Operator

1. **Monitor aggregations**
   - Watch `data/round_state.json` for current round
   - Check `models/global/` for aggregated models
   - Review logs for submission errors

2. **Handle missing submissions**
   - Current: waits forever
   - Phase 3: add timeout (aggregates after deadline)

3. **Detect Byzantine attacks** (Phase 3)
   - Current: weights weighted by sample count
   - Phase 3: Krum/median/trimmed mean detection

## Summary

Phase 2 adds server-side aggregation:

```
✓ RoundManager: tracks which hospitals submitted
✓ FedAvgAggregator: weights hospitals' models
✓ Automatic trigger: aggregate when all submit
✓ Download endpoint: hospitals get aggregated model
✓ Status endpoint: website shows coordination progress
✓ Notebook integration: hospitals load server model
```

Result: **Hospitals train independently, server aggregates, everyone benefits from shared learning.**

## Testing Commands

```bash
# Run all Phase 2 tests
python test_phase2_workflow.py

# Check round status
python -c "
from server.round_manager import get_round_manager
rm = get_round_manager()
print(rm.get_round_status())
"

# Check global models
python -c "
import os
from pathlib import Path
models = sorted(Path('models/global').glob('*.pt'))
for m in models:
    print(f'{m.name}: {m.stat().st_size} bytes')
"

# View round state
python -c "
import json
with open('data/round_state.json') as f:
    print(json.dumps(json.load(f), indent=2))
"
```

Enjoy federated learning! 🚀
