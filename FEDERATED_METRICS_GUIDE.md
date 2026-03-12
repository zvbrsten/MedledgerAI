# Federated Learning Metrics Integration Guide

## Overview

This document describes how the MedLedger-AI website displays federated learning model training status from externally-exported artifacts.

**Core Principle:** The website is **read-only** with respect to the training pipeline. It never executes, triggers, or modifies model training.

---

## Architecture

### Training Pipeline (Jupyter Notebook)
- **Location:** `Medledger_rev2.ipynb` (executed in Google Colab or locally)
- **Output:** Exports `federated_metrics.json` after training completes
- **Scope:** Implements FedAvg algorithm, manages hospital data, trains global model

### Website (Flask + Templates)
- **Location:** `app.py` and `/templates/`
- **Input:** Reads `federated_metrics.json` from `/data/` directory
- **Scope:** Displays metrics, renders charts, provides institutional dashboards
- **Constraint:** No training logic, no ML imports, no file writes

---

## File Structure

```
MedLedger-AI/
├── Medledger_rev2.ipynb          # Training notebook (exports metrics)
├── app.py                          # Flask app with /federated-metrics route
├── metrics_loader.py               # Utility to read JSON artifacts
├── data/
│   └── federated_metrics.json      # Exported metrics snapshot (created by notebook)
├── templates/
│   ├── federated_metrics.html      # Dashboard displaying metrics & charts
│   └── admin.html                  # Links to metrics page
└── static/
    └── style.css                   # Styling for charts and layout
```

---

## Exported Metrics Format

The notebook exports a JSON file to `federated_metrics.json` with the following structure:

```json
{
  "model_id": "medledger_global_v1",
  "last_updated": "2026-01-29T14:32:00",
  "institutions_participated": 5,
  "training_rounds": 10,
  "accuracy_per_round": [0.71, 0.734, 0.762, ...],
  "loss_per_round": [0.68, 0.61, 0.55, ...],
  "final_accuracy": 89.50,
  "model_status": "available"
}
```

**Required Fields:**
- `model_id`: Unique identifier for this trained model version
- `last_updated`: ISO 8601 timestamp of training completion
- `institutions_participated`: Number of institutions in federated round
- `training_rounds`: Total FL rounds completed
- `final_accuracy`: Final test set accuracy (percentage)
- `model_status`: One of `"available"`, `"training"`, `"unavailable"`

**Optional Fields:**
- `accuracy_per_round`: Array of accuracy values per round (for charting)
- `loss_per_round`: Array of loss values per round (for charting)

---

## Backend Integration

### metrics_loader.py

A lightweight utility that reads and validates exported metrics:

```python
from metrics_loader import load_federated_metrics, get_model_status_text, format_timestamp

# Load metrics from /data/ directory
metrics = load_federated_metrics('/path/to/data')

# Check if metrics are available
if metrics['available']:
    print(f"Model: {metrics['model_id']}")
    print(f"Accuracy: {metrics['final_accuracy']}%")
```

**Key Functions:**

1. **`load_federated_metrics(data_dir)`**
   - Reads `federated_metrics.json`
   - Validates required fields
   - Returns dict with `available=True/False`
   - Fails gracefully (returns default dict, no exceptions)

2. **`get_model_status_text(metrics)`**
   - Converts `model_status` to human-readable string
   - Returns: "Trained Model Available", "Training in Progress", etc.

3. **`format_timestamp(iso_string)`**
   - Converts ISO 8601 to readable format
   - Returns: "2026-01-29 14:32:00 UTC" or "Unknown"

---

## Frontend Display

### Route: `/federated-metrics`

**Location:** `app.py`

```python
@app.route('/federated-metrics')
def federated_metrics():
    metrics = load_federated_metrics(DATA_DIR)
    if metrics.get("available"):
        metrics["last_updated_formatted"] = format_timestamp(metrics.get("last_updated"))
        metrics["status_text"] = get_model_status_text(metrics)
    return render_template('federated_metrics.html', metrics=metrics)
```

**Features:**
- Reads `/data/federated_metrics.json`
- Formats timestamp for display
- Renders HTML with model status and charts
- Handles missing artifacts gracefully

### Template: `federated_metrics.html`

Displays:

1. **Model Status Panel** (when available)
   - Model Identifier
   - Training Rounds
   - Participating Institutions
   - Final Accuracy
   - Last Updated Timestamp

2. **Training Accuracy Chart**
   - Line chart using Chart.js
   - X-axis: Training round (1 to N)
   - Y-axis: Accuracy (0% to 100%)
   - Data source: `accuracy_per_round` array

3. **Training Loss Chart**
   - Line chart using Chart.js
   - X-axis: Training round (1 to N)
   - Y-axis: Loss value
   - Data source: `loss_per_round` array

4. **Unavailable State**
   - Gray info panel when no metrics found
   - Message directing to artifact location

---

## Workflow: How Metrics Get Displayed

### Step 1: Notebook Training (Colab/Local)
```
Researcher runs Medledger_rev2.ipynb
    ↓
FedAvg algorithm trains across hospitals
    ↓
Notebook evaluates final model accuracy
    ↓
Notebook exports to /export/federated_metrics.json
```

### Step 2: Artifact Deployment
```
Download /export/federated_metrics.json from Colab
    ↓
Place into website /data/ directory
    ↓
Website auto-detects on next page load
```

### Step 3: Website Display
```
User visits http://site/federated-metrics
    ↓
Flask route calls load_federated_metrics()
    ↓
Reads /data/federated_metrics.json
    ↓
Renders charts and status panel
```

---

## Safety & Constraints

✅ **What This Integration DOES:**
- Read exported JSON files
- Display metrics on dashboards
- Render training progress charts
- Format timestamps and status text

❌ **What This Integration DOES NOT DO:**
- Execute the notebook
- Run training logic
- Modify exported artifacts
- Write to the filesystem
- Import PyTorch or ML libraries
- Connect to Colab or training runtime

This strict separation ensures:
- **Security:** No ML code on web server
- **Privacy:** Healthcare data stays in controlled environment
- **Simplicity:** Website is stateless and scalable
- **Auditability:** Clear artifact-based handoff

---

## Troubleshooting

### Metrics Not Appearing
1. Verify `federated_metrics.json` exists in `/data/`
2. Check file format matches JSON schema
3. Ensure all required fields are present
4. Check file permissions (readable by Flask process)

### Charts Not Rendering
1. Ensure `accuracy_per_round` and `loss_per_round` are arrays
2. Verify values are numeric
3. Check Chart.js CDN is accessible
4. Browser console for JavaScript errors

### Invalid Timestamp
1. Verify `last_updated` is ISO 8601 format
2. Accept: `"2026-01-29T14:32:00"` or `"2026-01-29T14:32:00Z"`
3. If invalid, display shows "Unknown"

---

## Future Enhancements (Not Implemented)

The following are explicitly NOT implemented in Phase-1:
- Model update requests from web UI
- Artifact replacement workflows
- Live training status polling
- Automatic model versioning
- Blockchain audit trail

These are architectural decisions for Phase-2.

---

## References

- **Notebook Export Cell:** `Medledger_rev2.ipynb` (Cell 17, lines 292-344)
- **Metrics Loader:** `metrics_loader.py`
- **Flask Route:** `app.py` (line ~156)
- **Template:** `templates/federated_metrics.html`
- **Sample Data:** `data/federated_metrics.json`
