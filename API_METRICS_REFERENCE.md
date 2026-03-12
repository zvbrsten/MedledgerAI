# API Endpoint: Append Metrics Round

## Endpoint Details

**URL:** `/api/append-metrics-round`  
**Method:** `POST`  
**Authentication:** Admin only  
**Content-Type:** `application/json`

## Purpose

Allows programmatic addition of new federated learning training rounds to the metrics system. Used when:
- Training pipeline completes in Jupyter notebook
- Automated training orchestrators finish a round
- Manual metrics submission after off-line training

## Request Format

```json
POST /api/append-metrics-round

{
  "round": 12,
  "accuracy": 0.908,
  "precision": 0.891,
  "recall": 0.921,
  "f1_score": 0.906,
  "loss": 0.205,
  "auc_roc": 0.937,
  "institutions_participated": 5,
  "samples_processed": 22000,
  "timestamp": "2026-01-30T15:30:00"
}
```

## Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `round` | int | ✓ | Round number |
| `accuracy` | float | ✓ | Accuracy (0.0-1.0) |
| `precision` | float | ✓ | Precision (0.0-1.0) |
| `recall` | float | ✓ | Recall (0.0-1.0) |
| `f1_score` | float | ✓ | F1 Score (0.0-1.0) |
| `loss` | float | ✓ | Loss value |
| `auc_roc` | float | ✓ | AUC-ROC (0.0-1.0) |
| `institutions_participated` | int | ✗ | Number of hospitals (default: 5) |
| `samples_processed` | int | ✗ | Total samples processed (default: 20000) |
| `timestamp` | string | ✗ | ISO 8601 timestamp (auto-generated if omitted) |

## Success Response (200)

```json
{
  "success": true,
  "message": "Round 12 appended successfully",
  "round": 12,
  "metrics": {
    "accuracy": 0.908,
    "precision": 0.891,
    "recall": 0.921,
    "f1_score": 0.906,
    "loss": 0.205,
    "auc_roc": 0.937
  }
}
```

## Error Responses

### 401 - Unauthorized (Admin login required)
```json
{
  "success": false,
  "error": "Admin access required"
}
```

### 400 - Missing required fields
```json
{
  "success": false,
  "error": "Missing required fields"
}
```

### 404 - Metrics file not found
```json
{
  "success": false,
  "error": "Metrics file not found"
}
```

### 500 - Server error
```json
{
  "success": false,
  "error": "Error message details"
}
```

## Examples

### Using cURL

```bash
# Admin login first (get session cookie)
curl -c cookies.txt -X POST http://localhost:5000/login \
  -d "username=admin&password=adminpass"

# Then append metrics with authentication
curl -b cookies.txt -X POST http://localhost:5000/api/append-metrics-round \
  -H "Content-Type: application/json" \
  -d '{
    "round": 12,
    "accuracy": 0.908,
    "precision": 0.891,
    "recall": 0.921,
    "f1_score": 0.906,
    "loss": 0.205,
    "auc_roc": 0.937,
    "institutions_participated": 5,
    "samples_processed": 22000
  }'
```

### Using Python

```python
import requests
import json

# Establish session with login
session = requests.Session()
session.post(
    'http://localhost:5000/login',
    data={'username': 'admin', 'password': 'adminpass'}
)

# Append new metrics round
metrics_data = {
    "round": 12,
    "accuracy": 0.908,
    "precision": 0.891,
    "recall": 0.921,
    "f1_score": 0.906,
    "loss": 0.205,
    "auc_roc": 0.937,
    "institutions_participated": 5,
    "samples_processed": 22000
}

response = session.post(
    'http://localhost:5000/api/append-metrics-round',
    json=metrics_data
)

print(response.json())
```

### Using JavaScript/Fetch

```javascript
// First login
await fetch('http://localhost:5000/login', {
  method: 'POST',
  credentials: 'include',
  body: new FormData(loginForm)
});

// Then append metrics
const metricsData = {
  "round": 12,
  "accuracy": 0.908,
  "precision": 0.891,
  "recall": 0.921,
  "f1_score": 0.906,
  "loss": 0.205,
  "auc_roc": 0.937,
  "institutions_participated": 5,
  "samples_processed": 22000
};

const response = await fetch('http://localhost:5000/api/append-metrics-round', {
  method: 'POST',
  credentials: 'include',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(metricsData)
});

const result = await response.json();
console.log(result);
```

## Integration with Jupyter Notebook

After federated learning training completes:

```python
import requests
import json

# Your metrics from training
metrics = {
    "round": current_round,
    "accuracy": 0.908,
    "precision": 0.891,
    "recall": 0.921,
    "f1_score": 0.906,
    "loss": 0.205,
    "auc_roc": 0.937,
    "institutions_participated": num_hospitals,
    "samples_processed": total_samples
}

# Send to website
try:
    response = requests.post(
        'http://localhost:5000/api/append-metrics-round',
        json=metrics,
        cookies={'session': session_cookie}  # Need to authenticate first
    )
    print("Metrics appended:", response.json())
except Exception as e:
    print("Error appending metrics:", e)
```

## Notes

- The endpoint **appends** new rounds, never overwrites existing data
- Complete audit trail is maintained
- All previous rounds remain accessible
- Website displays updated metrics immediately after successful append
- Timestamp defaults to current UTC time if not provided
- All metric values are stored as-is (recommend 0-1 range for classification metrics)
