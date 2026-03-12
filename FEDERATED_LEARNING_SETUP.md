# Federated Learning: Secure Model Update System

## Overview

This federated learning system implements a **privacy-preserving architecture** where:

- ✅ **Hospital data remains LOCAL** - Datasets never leave hospital machines
- ✅ **Server receives only model weights** - Not data, not images, only trained weights
- ✅ **Secure authentication** - Per-hospital API tokens via X-API-KEY header
- ✅ **Integrity verification** - SHA-256 hashing of all submissions
- ✅ **Audit trail** - Metadata logging with hospital, timestamp, and IP address
- ✅ **No aggregation yet** - Server stores weights, aggregation is future work

## Architecture

### Data Flow

```
Hospital Machine                          Central Server
==============                            ==============

Local Dataset                                models/
(chest X-rays)                              ├── incoming/
    ↓                                         │   └── hospital_1/
    │                                         │       └── round_3/
Train Model                                  │           ├── weights.pt
    ↓                                         │           ├── weights.sha256
    │                                         │           └── metadata.json
Export Weights                               └── ...
(no data)                                   
    ↓
Export Metrics                           
(accuracy, loss, samples)
    ↓
POST /api/submit_update
(X-API-KEY header)
    ├─────────────────────────────────────→ Validate API key
                                            ↓
                                            Validate file (type, size)
                                            ↓
                                            Check metrics JSON
                                            ↓
                                            Compute SHA-256
                                            ↓
                                            Save weights + metadata
                                            ↓
    ←─────────────────────────────────────  HTTP 200 success
Success confirmation
```

## Setup Instructions

### 1. Server-Side Setup

#### a. API Token Configuration

Create `config/hospitals.json` with pre-shared API tokens for each hospital:

```json
{
  "hospital_1": "hospital1_token_abc123def456xyz789",
  "hospital_2": "hospital2_token_xyz789abc123def456",
  "hospital_3": "hospital3_token_def456xyz789abc123",
  "hospital_4": "hospital4_token_789abc123def456xyz",
  "hospital_5": "hospital5_token_456xyz789abc123def"
}
```

**IMPORTANT**: 
- This file should be **git-ignored** (added to .gitignore)
- Tokens should be provisioned **out-of-band** (not in source control)
- Each hospital receives their unique token via secure channel
- Production: Use environment variables instead of config files

#### b. Verify Server is Running

```bash
# Terminal 1: Start Flask server
python app.py

# Should output:
# * Running on http://0.0.0.0:5000
```

#### c. Check Directory Structure

The server will create this structure automatically:

```
project/
├── config/
│   └── hospitals.json          (pre-shared API tokens)
├── models/
│   └── incoming/
│       ├── hospital_1/
│       │   └── round_3/
│       │       ├── weights.pt       (model weights file)
│       │       ├── weights.sha256   (integrity hash)
│       │       └── metadata.json    (audit metadata)
│       ├── hospital_2/
│       │   └── round_2/
│       │       └── ...
│       └── ...
└── app.py
```

### 2. Hospital-Side Setup (Using Notebook)

#### a. Open Notebook

```bash
jupyter notebook Medledger_rev2.ipynb
```

#### b. Add Hospital Configuration

In the new "Step 6" cell, update:

```python
HOSPITAL_ID = "hospital_1"    # Your hospital ID
CURRENT_ROUND = 1              # Increment after each training
```

#### c. Get API Key

Replace `API_KEY` in "Step 8" cell with:

**Option 1 (Development)**: Load from local config
```python
API_KEY = "hospital1_token_abc123def456xyz789"
```

**Option 2 (Recommended)**: Use environment variable
```bash
export HOSPITAL_API_KEY="hospital1_token_abc123def456xyz789"
```

Then in notebook:
```python
API_KEY = os.environ.get('HOSPITAL_API_KEY')
```

**Option 3 (Testing)**: Load from config/hospitals.json
```python
# Automatically handled in Step 8 cell
# (only for development, not recommended for production)
```

#### d. Run Training Cells (Steps 1-5)

Execute the existing training cells to train your model:
- Step 1: Import libraries
- Step 2: Load data
- Step 3: Build model
- Step 4: Training loop
- Step 5: Evaluation

#### e. Run Export Cells (Steps 6-7)

Execute the new export cells:
- **Step 6**: Exports local model weights to `local_model_roundN.pt`
- **Step 7**: Exports training metrics to `metrics_roundN.json`

The cell will confirm:
```
✓ Model weights exported: local_model_round1.pt
  File size: 45.32 MB
  Hospital: hospital_1
  Training round: 1

SECURITY: This file contains ONLY trained model weights.
No patient data, images, or datasets are included.
```

#### f. Run Submission Cell (Step 8)

Execute the submission cell to upload to server:

```python
# Should output:
✓ API key loaded for hospital_1
✓ Files ready:
  Weights: local_model_round1.pt (45.32 MB)
  Metrics: metrics_round1.json

✓ Metrics loaded: accuracy=0.8638, loss=0.3600

Submitting to http://localhost:5000/api/submit_update...

Server Response (200):
{
  "success": true,
  "message": "Model update for round 1 received successfully",
  "metadata_id": "hospital_1_round1"
}

============================================================
✓ MODEL UPDATE SUBMITTED SUCCESSFULLY
============================================================
Submission ID: hospital_1_round1
Message: Model update for round 1 received successfully

SECURITY SUMMARY:
✓ Weights file sent securely to server
✓ Metrics JSON sent with model
✓ Server stored weights and metadata
✓ Hospital data remained on this machine
```

### 3. Testing Without Notebook

Use the provided test script `client_test_upload.py`:

```bash
# Test with defaults (hospital_1, round 1, dummy weights)
python client_test_upload.py

# Test with specific hospital
python client_test_upload.py --hospital-id hospital_2 --round 2

# Test with custom metrics
python client_test_upload.py \
  --hospital-id hospital_1 \
  --round 3 \
  --accuracy 0.9054 \
  --loss 0.22

# Test with real weights file
python client_test_upload.py \
  --hospital-id hospital_1 \
  --round 1 \
  --weights my_model_weights.pt \
  --accuracy 0.8638 \
  --loss 0.36
```

## API Endpoint Reference

### POST /api/submit_update

Submit a model update to the coordination server.

**Authentication**: X-API-KEY header (required)

**Request (multipart/form-data)**:

```bash
curl -X POST http://localhost:5000/api/submit_update \
  -H "X-API-KEY: hospital1_token_abc123def456xyz789" \
  -F "hospital_id=hospital_1" \
  -F "round=1" \
  -F "weights=@local_model_round1.pt" \
  -F "metrics={\"accuracy\": 0.8638, \"loss\": 0.36, \"num_samples\": 100}"
```

**Form Fields**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `hospital_id` | string | ✓ | Hospital identifier (e.g., "hospital_1") |
| `round` | integer | ✓ | Training round number (≥ 1) |
| `weights` | file | ✓ | Model weights file (.pt or .pth only) |
| `metrics` | JSON string | ✓ | Metrics JSON (see below) |

**Metrics JSON Format**:

```json
{
  "accuracy": 0.8638,
  "loss": 0.36,
  "num_samples": 100,
  "timestamp": "2024-01-30T14:45:00Z"
}
```

Required fields: `accuracy`, `loss`
Optional fields: `num_samples`, `timestamp` (auto-generated if omitted)

**Response (HTTP 200 Success)**:

```json
{
  "success": true,
  "message": "Model update for round 1 received successfully",
  "metadata_id": "hospital_1_round1"
}
```

**Error Responses**:

| Code | Error | Meaning |
|------|-------|---------|
| 400 | Missing hospital_id | Form field missing |
| 401 | Missing X-API-KEY header | Auth header missing |
| 401 | Invalid API key | Token doesn't match hospital |
| 400 | Invalid round number | Round must be integer ≥ 1 |
| 400 | Round already submitted | Round number not greater than previous |
| 400 | Missing weights file | File field missing |
| 400 | Invalid file type | File not .pt or .pth |
| 413 | File too large | Exceeds 200 MB limit |
| 400 | Invalid metrics JSON | JSON malformed or missing required fields |
| 429 | Rate limit exceeded | > 10 requests per minute from hospital |

## Security Considerations

### Authentication
- **X-API-KEY header**: Pre-shared tokens unique to each hospital
- **Per-hospital isolation**: Tokens stored in config/hospitals.json
- **Timing-safe comparison**: API key validation resistant to timing attacks

### File Validation
- **Extension whitelist**: Only .pt and .pth files accepted
- **Size limits**: Maximum 200 MB per submission (configurable)
- **SHA-256 hashing**: All files hashed for tamper detection
- **Monotonic rounds**: Prevents re-submission of old rounds

### Data Privacy
- **No dataset upload**: Only model weights + metrics accepted
- **No file paths in responses**: Server doesn't return file locations to client
- **Metadata logging**: Audit trail stored separately from weights
- **Hospital data stays local**: Patient data never leaves hospital machines

### Rate Limiting
- **10 requests per minute per hospital**: Prevents spam/DOS
- **In-memory throttling**: Simple, fast rate limiting
- **Per-hospital isolation**: Each hospital has independent limit

### Production Deployment

For production use, implement these security upgrades:

1. **HTTPS/TLS**: Use SSL certificates
   ```python
   # In app.py
   # app.run(ssl_context='adhoc')  # or with cert files
   ```

2. **Environment Variables**: Store API keys in environment, not config files
   ```bash
   export HOSPITAL_1_API_KEY="..." 
   export HOSPITAL_2_API_KEY="..."
   ```

3. **Key Rotation**: Implement token expiration and refresh
   ```python
   # FUTURE: Add token expiration logic
   ```

4. **Database**: Move rate limiting to persistent database
   ```python
   # FUTURE: Use Redis for distributed rate limiting
   ```

5. **Monitoring**: Log and alert on suspicious activity
   ```python
   # FUTURE: Add anomaly detection
   ```

## Metadata Storage Format

Server stores metadata for each submission:

```json
{
  "hospital_id": "hospital_1",
  "round": 3,
  "filename": "weights.pt",
  "sha256": "a1b2c3d4e5f6...",
  "file_size_bytes": 47451680,
  "metrics": {
    "accuracy": 0.8638,
    "loss": 0.36,
    "num_samples": 100,
    "timestamp": "2024-01-30T14:45:00Z"
  },
  "received_at": "2024-01-30T14:45:23Z",
  "uploader_ip": "192.168.1.100"
}
```

This metadata is used for:
- Audit trail and compliance
- Validation and integrity checking
- Future aggregation logic
- Performance monitoring

## Troubleshooting

### Server won't start

```bash
# Check if port 5000 is in use
lsof -i :5000

# Try different port
python app.py --port 5001

# Check Flask is installed
pip install flask werkzeug requests
```

### Submission fails with 401 (Unauthorized)

```
Error: Invalid API key for hospital

Solution:
1. Verify API key is correct for your hospital_id
2. Check X-API-KEY header is being sent
3. Confirm config/hospitals.json exists and is valid
4. Check hospital_id matches between notebook and config
```

### Submission fails with 413 (File too large)

```
Error: File too large. Maximum size: 200 MB

Solution:
1. Model weights file exceeds 200 MB
2. Quantize or prune model to reduce size
3. Use model compression techniques
4. Update MAX_WEIGHT_FILE_SIZE in app.py (not recommended)
```

### Submission fails with 400 (Round already submitted)

```
Error: Round 1 already submitted or lower than previous round

Solution:
1. Increment CURRENT_ROUND in notebook
2. Check previously submitted rounds:
   python3 -c "import json; \
   d='models/incoming/hospital_1'; \
   print([int(x.split('_')[1]) for x in os.listdir(d) if x.startswith('round_')])"
3. Each round must have unique, increasing round numbers
```

### Connection refused error

```
Error: Connection error: Cannot reach http://localhost:5000

Solution:
1. Start Flask server first: python app.py
2. Check server is running: curl http://localhost:5000
3. Verify firewall allows localhost connections
4. Check SERVER_URL in notebook matches Flask server URL
```

## Future Enhancements

Hooks for future implementation (marked with `FUTURE` in code):

```python
# FUTURE: call_aggregation(hospital_id, round_num, weights_path, metadata)
# - Aggregate weights from multiple hospitals
# - Compute weighted average or federated learning algorithm
# - Distribute global model back to hospitals

# FUTURE: Implement federated averaging (FedAvg)
# - Parameter aggregation across hospitals
# - Privacy-preserving aggregation with differential privacy

# FUTURE: Add model versioning
# - Track model versions across aggregation rounds
# - Enable rollback to previous versions

# FUTURE: Implement token expiration
# - Time-limited API keys
# - Refresh token mechanism

# FUTURE: Add anomaly detection
# - Detect suspicious model updates
# - Flag outlier metrics
```

## References

- PyTorch model saving: https://pytorch.org/tutorials/beginner/saving_loading_models.html
- Federated Learning: https://en.wikipedia.org/wiki/Federated_learning
- REST API design: https://restfulapi.net/
- HTTP Security headers: https://owasp.org/www-project-secure-headers/

## Support

For issues or questions:

1. Check troubleshooting section above
2. Review server logs: `tail -f logs/federated_learning.log`
3. Test with `client_test_upload.py` to isolate issues
4. Verify config/hospitals.json is valid JSON
5. Check file permissions for models/incoming/ directory
