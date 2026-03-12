# Phase 2: Server-Side Federated Aggregation

## Overview

Phase 2 implements **server-side FedAvg aggregation** for the MedLedger federated learning system. This phase completes the federated learning loop by enabling the server to aggregate hospital-submitted model weights and distribute the aggregated model back to hospitals.

## Mental Model

```
HOSPITALS              SERVER                WEBSITE
    │                    │                      │
    ├─ Train locally     │                      │
    │                    │                      │
    ├─ Submit weights───→│                      │
    │                    │                      │
    │              ┌─────┴─────┐                │
    │              │ Waiting   │                │
    │         [1/5, 2/5, ...] │                │
    │              └─────┬─────┘                │
    │                    │                      │ Shows status
    │              ┌─────▼─────┐               ◄─ Updates every 5s
    │              │ Aggregate │                │
    │              │  (FedAvg) │                │
    │              │ All rcvd? │                │
    │              └─────┬─────┘                │
    │                    │                      │
    ◄──────────────── Model ────────────────────┤
    │              (round N)                    │
    │                    │                      │
    └─ Next round      │                      │
```

**Golden Rule:**
```
"Hospitals train.
 Server aggregates.
 Website observes."
```

## What's New in Phase 2

### 2.1 Round State Manager (`server/round_manager.py`)

Tracks federated learning round coordination:
- Current round number
- Expected number of hospitals
- Which hospitals have submitted
- Aggregation status

**Key Methods:**
```python
rm = get_round_manager()
status = rm.register_submission(hospital_id, weights_path, num_samples)
# → Returns: "round_complete" when all hospitals submitted

status = rm.get_round_status()
# → Returns: current_round, received_hospitals, ready_for_aggregation

rm.mark_aggregation_complete(global_model_path)
# → Saves global model reference and increments round
```

**Persistent Storage:**
```json
// data/round_state.json
{
  "current_round": 1,
  "expected_hospitals": 5,
  "received_updates": ["hospital_1", "hospital_2"],
  "submissions": {
    "hospital_1": {
      "weights_path": "models/incoming/hospital_1/round_1/weights.pt",
      "num_samples": 500,
      "timestamp": "2026-01-30T12:00:00Z"
    }
  },
  "aggregation_status": "pending",
  "last_aggregation": null
}
```

### 2.2 FedAvg Aggregation Engine (`server/fedavg.py`)

Pure mathematical aggregation of model weights.

**Algorithm:**
```
global_model = Σ(weight_i * local_model_i) / Σ(weight_i)
where weight_i = num_samples_i / total_samples
```

**Key Method:**
```python
aggregator = FedAvgAggregator()
success, msg, metadata = aggregator.aggregate(
    submissions={
        "hospital_1": ("path/weights.pt", 500),
        "hospital_2": ("path/weights.pt", 480),
        ...
    },
    global_round=1,
    output_dir="models/global"
)
# → Creates: models/global/global_model_round1.pt
```

**Security Notes:**
- ✓ Only reads .pt files (model parameters)
- ✓ Performs parameter-wise weighted averaging
- ✗ Never accesses raw data
- ✗ Never executes PyTorch training
- ✗ Never modifies hospital files

### 2.3 Automatic Aggregation Trigger (in `app.py`)

When hospital submits weights via `POST /api/submit_update`:

1. **Register submission** via RoundManager
2. **Check if all hospitals submitted** → `ready_for_aggregation = True`
3. **If yes, automatically trigger FedAvg:**
   - Load all hospital weights
   - Compute weighted average
   - Save global_model_roundN.pt
   - Increment round number
   - Reset submission tracker

**Code Flow:**
```python
@app.route('/api/submit_update', methods=['POST'])
def submit_model_update():
    # ... validate submission ...
    
    # Register with round manager
    submission_status = rm.register_submission(hospital_id, weights_path, num_samples)
    
    # Check if all hospitals submitted
    if submission_status['ready_for_aggregation']:
        # Automatically trigger aggregation
        aggregator = FedAvgAggregator()
        success, msg, metadata = aggregator.aggregate(submissions, round_num)
        
        if success:
            # Mark complete and increment round
            rm.mark_aggregation_complete(metadata['global_model_path'])
```

**Result:** ✓ Deterministic, idempotent, no race conditions

### 2.4 Global Model Distribution Endpoint

**Endpoint:** `GET /api/global-model/latest`

```python
@app.route('/api/global-model/latest', methods=['GET'])
def get_global_model():
    # Find latest aggregated model
    # Return as file download
    # Include metadata headers:
    #   X-GLOBAL-ROUND: current round
    #   X-MODEL-HASH: SHA-256 for verification
```

**Usage in Hospital Notebook:**
```python
response = requests.get(
    "http://server:5000/api/global-model/latest"
)
# response.headers['X-GLOBAL-ROUND'] = "1"
# Save: global_model_round1.pt
```

**Security:**
- ✓ No authentication (prototype)
- ✓ Returns only model file
- ✗ No data exposure

### 2.5 Round Status Coordination Endpoint

**Endpoint:** `GET /api/round-status`

```json
{
  "current_round": 1,
  "expected_hospitals": 5,
  "received_hospitals": ["hospital_1", "hospital_2"],
  "missing_hospitals": ["hospital_3", "hospital_4", "hospital_5"],
  "ready_for_aggregation": false,
  "aggregation_status": "pending"
}
```

**Usage:**
- Hospitals check if previous round aggregated
- Website displays coordination status
- Admin knows when all hospitals submitted

### 2.6 Hospital Notebook Integration (Minimal Change)

**Added Cell 2 (after configuration):**
```python
def download_global_model(server_url, current_round):
    """Download aggregated model from previous round"""
    if current_round == 1:
        return True, None, None  # No previous model yet
    
    # For round >= 2, download from server
    response = requests.get(f"{server_url}/api/global-model/latest")
    if response.status_code == 200:
        # Save and return path
        return True, "global_model_roundN.pt", N
    return False, None, None
```

**Updated Cell 8 (Load Global Model):**
```python
if CURRENT_ROUND == 1:
    global_model = fresh_model()  # Start from base
else:
    if downloaded_global_model_exists:
        global_model = load(downloaded_global_model)  # Use aggregated
    else:
        global_model = fresh_model()  # Fallback
```

**Impact:** ✓ Hospital loads server-aggregated model instead of creating its own

### 2.7 Website Round Coordination Display

**New Section on `/model-status` page:**

```html
<!-- Federated Learning Coordination Status -->
<section>
  <h2>⚙️ Coordination Status</h2>
  
  <div>
    <h4>Current Round</h4>
    <p>{{ status.current_round }}</p>
  </div>
  
  <div>
    <h4>Hospital Submissions</h4>
    <p>{{ received }} / {{ expected }}</p>
  </div>
  
  <div>
    <h4>Aggregation Status</h4>
    <p>{{ aggregation_status }}</p>
  </div>
  
  <div>
    <h4>Hospital Status</h4>
    <div>
      ✓ hospital_1 (submitted)
      ✓ hospital_2 (submitted)
      ⧗ hospital_3 (waiting)
      ⧗ hospital_4 (waiting)
      ⧗ hospital_5 (waiting)
    </div>
  </div>
</section>
```

**JavaScript:**
- Fetches `/api/round-status` every 5 seconds
- Updates UI in real-time
- Shows which hospitals have submitted
- Shows aggregation progress

## Complete Phase 2 Workflow

### Round N Workflow

```
TIME    HOSPITAL ACTIONS              SERVER ACTIONS            WEBSITE SHOWS
────────────────────────────────────────────────────────────────────────────────
T0      Hospital A trains locally
        Hospital B trains locally
        Hospital C trains locally
        Hospital D trains locally
        Hospital E trains locally

T1      Hospital A submits            Receives & stores
        weights + metrics             Register in RoundManager   Round 1
                                                                 1/5 submitted

T2      Hospital B submits            Receives & stores
                                      Register in RoundManager   2/5 submitted

T3      Hospital C submits            Receives & stores
                                      Register in RoundManager   3/5 submitted

T4      Hospital D submits            Receives & stores
                                      Register in RoundManager   4/5 submitted

T5      Hospital E submits            Receives & stores
                                      Detects: ALL 5 RECEIVED    5/5 submitted
                                      ↓
                                      Triggers FedAvg
                                      ↓
                                      Loads all 5 weights
                                      ↓
                                      Computes weighted average
                                      ↓
                                      Saves global_model_round1.pt
                                      ↓
                                      Increments to Round 2
                                      ↓
                                      Resets submission tracker   Aggregating...
                                      
T6                                    Aggregation complete       Round 2
                                                                 Aggregated ✓
                                                                 
T7      Hospital A downloads          Serves global_model_       Downloaded
        aggregated model              round1.pt with headers
        
        Hospital B downloads
        ...
        Hospital E downloads

T8      All hospitals load
        server-aggregated model

T9      Round 2 training begins       Waiting for submissions    Round 2
        Hospital A trains locally                               0/5 submitted
        ...
        (Cycle repeats)
```

## Directory Structure

```
medledeger/
├── server/
│   ├── __init__.py
│   ├── fedavg.py              # FedAvg aggregation engine
│   └── round_manager.py       # Round state manager
│
├── data/
│   ├── round_state.json       # Persistent round state
│   └── federated_metrics.json # Training history
│
├── models/
│   ├── incoming/
│   │   ├── hospital_1/
│   │   │   └── round_1/
│   │   │       ├── weights.pt
│   │   │       ├── metadata.json
│   │   │       └── weights.sha256
│   │   ├── hospital_2/...
│   │   └── hospital_5/...
│   │
│   └── global/
│       ├── global_model_round1.pt
│       ├── global_model_round2.pt
│       └── global_model_round3.pt
│
└── app.py                     # Flask server with:
                               # - POST /api/submit_update (trigger)
                               # - GET /api/global-model/latest
                               # - GET /api/round-status
```

## API Reference

### Hospital Submission (Existing, Enhanced)

```http
POST /api/submit_update
Content-Type: multipart/form-data
X-API-KEY: pre-shared-token

hospital_id=hospital_1
round=1
weights=<binary .pt file>
metrics={"accuracy": 0.92, "loss": 0.15, "num_samples": 500}

RESPONSE 200:
{
  "success": true,
  "message": "Model update received",
  "aggregation_status": "registered" | "round_complete"
}
```

**NEW:** If `aggregation_status` is `"round_complete"`, all hospitals submitted!

### Global Model Download (NEW)

```http
GET /api/global-model/latest

RESPONSE 200 (binary):
<file contents>

Headers:
X-GLOBAL-ROUND: 1
X-MODEL-HASH: a3c4d5e6f7...
X-FILE-SIZE: 98765432

RESPONSE 404:
{
  "error": "No global model available yet",
  "message": "Waiting for first aggregation"
}
```

### Round Status (NEW)

```http
GET /api/round-status

RESPONSE 200:
{
  "current_round": 1,
  "expected_hospitals": 5,
  "received_hospitals": ["hospital_1", "hospital_2"],
  "missing_hospitals": ["hospital_3", "hospital_4", "hospital_5"],
  "ready_for_aggregation": false,
  "aggregation_status": "pending"
}
```

## Testing

Run the comprehensive Phase 2 test:

```bash
python test_phase2_workflow.py
```

**What it tests:**
1. Round state tracking (registration, increment)
2. FedAvg aggregation (mock weights)
3. Global model file creation
4. Round increment after aggregation
5. Model file verification
6. Architecture constraints (no data exposure)

**Output Example:**
```
✓ PHASE 2 TESTS PASSED

Federated Learning Aggregation Pipeline:
  1. ✓ Hospitals train locally (notebook)
  2. ✓ Hospitals submit weights + metrics to server
  3. ✓ Server detects all submissions
  4. ✓ Server performs FedAvg aggregation
  5. ✓ Global model saved to disk
  6. ✓ Round incremented
  7. → Hospitals download global model
  8. → Cycle repeats for next round
```

## Security & Privacy Checklist

- ✓ **No patient data on server**
  - Only .pt files (model weights) stored in `models/incoming/`
  - No image data, no metadata, no demographics
  
- ✓ **No training on server**
  - FedAvg is pure mathematical averaging
  - No PyTorch nn.Module training code executed
  
- ✓ **Deterministic aggregation**
  - All hospitals with same data produce same result
  - Idempotent: running aggregation twice = same output
  
- ✓ **Tamper detection**
  - SHA-256 hash computed for each submission
  - Stored in `weights.sha256` for verification
  
- ✓ **Audit logging**
  - All submissions logged (with metrics, not weights)
  - All aggregations logged
  - Round state transitions logged

## Known Limitations & Future Work

### Current Limitations

1. **No authentication for download** (proto mode)
   - Phase 3: Add hospital tokens to `/api/global-model/latest`

2. **No Byzantine robustness**
   - All hospitals weighted equally by sample count
   - Phase 3: Detect outlier submissions (Krum, trimmed mean)

3. **No versioning**
   - Only latest model available for download
   - Phase 3: Support downloading any round's model

4. **Synchronous submission**
   - Server waits for all hospitals (blocks)
   - Phase 3: Support asynchronous aggregation by deadline

### Next Steps (Phase 3)

- [ ] Add authentication to model download endpoint
- [ ] Implement Byzantine-robust aggregation (Krum, median, trimmed mean)
- [ ] Add model versioning (download any historical round)
- [ ] Implement round timeout (aggregate after deadline)
- [ ] Add hospital dropout handling (handle missing submissions)
- [ ] Implement differential privacy for weights

## Summary

Phase 2 successfully implements **server-side FedAvg aggregation**, completing the federated learning loop:

```
Hospital Training  ──→  Hospital Submission  ──→  Server Aggregation
      (local)            (weights + metrics)         (weighted avg)
                                                            ↓
                                                   Global Model ──→ Back to hospitals
```

The system now enforces the golden rule:
- **Hospitals train** (locally, with their own data)
- **Server aggregates** (weights only, no data exposure)
- **Website observes** (round coordination status)

✓ No patient data transferred
✓ No training on server
✓ Pure federated learning architecture
