# Quick Start: Testing Federated Learning Model Submission

This guide walks through testing the federated learning system in 5 minutes.

## Prerequisites

```bash
# Install required packages
pip install flask werkzeug requests torch

# Check installation
python3 -c "import flask, torch, requests; print('✓ All packages installed')"
```

## Step 1: Start the Flask Server (Terminal 1)

```bash
cd /path/to/Medledger
python app.py
```

Expected output:
```
 * Running on http://0.0.0.0:5000
 * Debug mode: on
```

**Keep this terminal open!**

## Step 2: Test with Test Script (Terminal 2)

### Option A: Quick Test (30 seconds)

```bash
cd /path/to/Medledger
python client_test_upload.py
```

Expected output:
```
✓ Loaded API key for hospital_1 from config/hospitals.json
Creating dummy weights file for testing...
============================================================
FEDERATED LEARNING: Model Update Submission
============================================================
Hospital ID:   hospital_1
Round:         1
Accuracy:      0.8638
Loss:          0.3600
Weights file:  local_model_test.pt
File size:     1.05 MB
Hash (SHA256): a1b2c3d4e5f6g7h8...
Endpoint:      http://localhost:5000/api/submit_update
============================================================

Submitting model update...

Response Code:  200
Response:       {
  "success": true,
  "message": "Model update for round 1 received successfully",
  "metadata_id": "hospital_1_round1"
}

✓ Model update submitted successfully!
  Submission ID: hospital_1_round1

Cleaned up test file: local_model_test.pt
```

### Option B: Test Different Hospital

```bash
python client_test_upload.py --hospital-id hospital_2 --round 1 --accuracy 0.9054
```

### Option C: Test with Real Weights File

```bash
python client_test_upload.py \
  --hospital-id hospital_1 \
  --round 2 \
  --weights my_model.pt \
  --accuracy 0.8638 \
  --loss 0.36 \
  --no-cleanup
```

## Step 3: Verify Server Stored the Model

Check the models directory was created:

```bash
# List all submissions
find models/incoming -type f -name "*.json"

# Example output:
# models/incoming/hospital_1/round_1/metadata.json
# models/incoming/hospital_1/round_2/metadata.json

# View metadata for a specific submission
cat models/incoming/hospital_1/round_1/metadata.json
```

Expected metadata:
```json
{
  "hospital_id": "hospital_1",
  "round": 1,
  "filename": "weights.pt",
  "sha256": "a1b2c3d4e5f6g7h8...",
  "file_size_bytes": 1048576,
  "metrics": {
    "accuracy": 0.8638,
    "loss": 0.36,
    "num_samples": 100,
    "timestamp": "2024-01-30T14:45:00Z"
  },
  "received_at": "2024-01-30T14:45:23Z",
  "uploader_ip": "127.0.0.1"
}
```

## Step 4: Test Authentication (Optional)

### Test 1: Missing API Key

```bash
curl -X POST http://localhost:5000/api/submit_update \
  -F "hospital_id=hospital_1" \
  -F "round=1" \
  -F "weights=@test.pt" \
  -F "metrics={\"accuracy\": 0.86, \"loss\": 0.36}"
```

Expected error:
```json
{"success": false, "error": "Missing X-API-KEY header"}
```

### Test 2: Invalid API Key

```bash
curl -X POST http://localhost:5000/api/submit_update \
  -H "X-API-KEY: invalid_key" \
  -F "hospital_id=hospital_1" \
  -F "round=1" \
  -F "weights=@test.pt" \
  -F "metrics={\"accuracy\": 0.86, \"loss\": 0.36}"
```

Expected error:
```json
{"success": false, "error": "Invalid API key for hospital"}
```

### Test 3: Valid API Key

```bash
curl -X POST http://localhost:5000/api/submit_update \
  -H "X-API-KEY: hospital1_token_abc123def456" \
  -F "hospital_id=hospital_1" \
  -F "round=1" \
  -F "weights=@test.pt" \
  -F "metrics={\"accuracy\": 0.86, \"loss\": 0.36}"
```

Expected success:
```json
{
  "success": true,
  "message": "Model update for round 1 received successfully",
  "metadata_id": "hospital_1_round1"
}
```

## Step 5: Test with Notebook (Optional)

### Option A: Using Medledger_rev2.ipynb

1. Open notebook:
   ```bash
   jupyter notebook Medledger_rev2.ipynb
   ```

2. Run training cells (steps 1-5)

3. Update step 6 cell:
   ```python
   HOSPITAL_ID = "hospital_1"
   CURRENT_ROUND = 6  # Use a new round number
   ```

4. Run step 6 (export weights)

5. Run step 7 (export metrics)

6. Run step 8 (submit to server)

### Option B: Testing Round Monotonicity

Test that the server rejects repeated round numbers:

```bash
# First submission succeeds
python client_test_upload.py --hospital-id hospital_3 --round 1

# Second submission with same round fails
python client_test_upload.py --hospital-id hospital_3 --round 1
```

Expected error on second:
```
"Round 1 already submitted or lower than previous round. Expected > 0"
```

## Cleanup

Remove test files:

```bash
# Remove test weights
rm -f local_model_test.pt local_model_round*.pt metrics_round*.json

# Reset a hospital's submissions (for retesting)
rm -rf models/incoming/hospital_1
```

## Troubleshooting

### "Connection error: Cannot reach http://localhost:5000"

**Solution**: Make sure Flask server is running in terminal 1
```bash
python app.py
```

### "config/hospitals.json not found or invalid"

**Solution**: config/hospitals.json exists but may need creation
```bash
# Create if missing
mkdir -p config
cat > config/hospitals.json << 'EOF'
{
  "hospital_1": "hospital1_token_abc123def456",
  "hospital_2": "hospital2_token_xyz789uvw012",
  "hospital_3": "hospital3_token_def456uvw789",
  "hospital_4": "hospital4_token_uvw789def456",
  "hospital_5": "hospital5_token_456uvw789abc"
}
EOF
```

### "File too large" error

**Solution**: Test file exceeds 200 MB
- Create smaller test file
- Or use existing .pt file < 200 MB

### "Rate limit exceeded"

**Solution**: Submitted > 10 times in 1 minute
- Wait 1 minute
- Or change hospital_id to test different hospital

## Success Checklist

- [ ] Flask server starts without errors
- [ ] client_test_upload.py runs successfully
- [ ] metadata.json created in models/incoming/
- [ ] API key validation works (test missing/invalid key)
- [ ] Round number validation works (test duplicate rounds)
- [ ] (Optional) Notebook integration works end-to-end

## Next Steps

Once testing is complete:

1. **Integrate with hospital notebook**: Update Medledger_rev2.ipynb steps 6-8 with hospital-specific values
2. **Provision API tokens**: Create unique tokens for each hospital via secure channel
3. **Implement aggregation**: Add federated averaging logic (see FEDERATED_LEARNING_SETUP.md)
4. **Deploy to production**: Set up HTTPS, environment variables, database-backed rate limiting
5. **Monitor submissions**: Set up logging and alerting on model updates

## More Information

- See FEDERATED_LEARNING_SETUP.md for detailed architecture and configuration
- See METRICS_GUIDE.md for tracking metrics across training
- See API_METRICS_REFERENCE.md for REST API endpoints
