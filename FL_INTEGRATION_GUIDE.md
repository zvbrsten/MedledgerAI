# MedLedger-AI: Federated Learning Integration Guide

## Overview

This document explains how the Federated Learning (FedAvg) training notebook integrates with the Flask website while maintaining **clean separation of concerns** and **healthcare privacy best practices**.

---

## Architecture: Why This Design?

### The Problem We Solve
Federated Learning requires:
- **Private training** (data stays with hospitals)
- **Decentralized aggregation** (no central server has raw data)
- **Secure deployment** (no live ML execution on public web servers)

But websites need:
- **Model status visibility** (accuracy, rounds, etc.)
- **Training orchestration** (start/stop controls)
- **Model versioning** (track improvements)

### Our Solution: Training → Artifacts → Website

```
┌──────────────────────────────────────────────────────────────┐
│  NOTEBOOK (Colab Environment)                                │
│  - Runs FedAvg training with hospital data                   │
│  - Computes accuracy, loss, rounds completed                 │
│  - Exports trained model + metrics → export.zip              │
│                                                               │
│  ✓ PyTorch here     ✓ Hospitals' data stays local            │
│  ✓ GPU training     ✓ No web dependencies                    │
└──────────────────────────────────────────────────────────────┘
                              ↓
                        export.zip downloaded
                              ↓
┌──────────────────────────────────────────────────────────────┐
│  FLASK WEBSITE (Django/Nginx deployment)                     │
│  - Reads global_model.pt (file existence check)              │
│  - Reads metrics.json (display only)                         │
│  - Shows model status on dashboards                          │
│                                                               │
│  ✗ No PyTorch import   ✗ No training execution               │
│  ✓ Safe read-only      ✓ Fast, stateless                     │
└──────────────────────────────────────────────────────────────┘
```

---

## Key Integration Points

### 1. Notebook Export Logic
**File:** `Medledger_rev2.ipynb` (last cell)

**What it does:**
```python
# Exports the trained global model
torch.save(global_model.state_dict(), "export/global_model.pt")

# Exports training metrics as JSON
metrics = {
    "rounds_completed": rounds,
    "accuracy": final_accuracy,
    "loss": loss_value,
    "last_updated": timestamp
}
```

**Why this matters:**
- ✅ Real values from training (no simulation)
- ✅ Timestamp for audit trail
- ✅ JSON format for easy parsing
- ✅ Deployable as a zip file

---

### 2. Flask Metrics Loader
**File:** `fl_integration.py`

**Public API:**
```python
load_metrics(models_dir, logs_dir) → Dict
```

**Features:**
- Safe file existence checks
- Handles missing files gracefully
- Returns "not trained yet" if no model exists
- JSON parsing with error handling

**Design Philosophy:**
- **No PyTorch imports** → Keeps Flask lightweight
- **No training execution** → Website is read-only
- **Defensive coding** → Handles corrupted/missing files

**Why this matters:**
- ✅ Website won't break if notebook hasn't run
- ✅ Easy to deploy without ML libraries
- ✅ Fast startup time for Flask app

---

### 3. Flask Route Integration
**File:** `app.py`

**Route `/admin`:**
```python
model_status = load_metrics(MODELS_DIR, LOGS_DIR)
return render_template('admin.html', hospitals=hospitals, model_status=model_status)
```

**Route `/model-status`:**
```python
status = load_metrics(MODELS_DIR, LOGS_DIR)
return render_template('model_status.html', status=status)
```

**Design Philosophy:**
- Metrics are loaded **on-demand** (each page request)
- No background jobs or polling
- Website is stateless and scalable

**Why this matters:**
- ✅ Always shows latest metrics
- ✅ No cache invalidation issues
- ✅ Suitable for distributed deployments

---

### 4. Template Integration
**Files:** `admin.html`, `model_status.html`

**What templates display:**

**Admin Dashboard:**
```
Global Model Status: ✓ Available
  - Rounds Completed: 5
  - Test Accuracy: 95.32%
  - Last Updated: 2025-01-29T14:32:10.123456
```

**Model Status Page:**
```
Model Trained and Available
  Rounds Completed: 5
  Test Accuracy: 95.32%
  Loss: 0.1234
  Last Updated: 2025-01-29T14:32:10.123456
```

**Design Philosophy:**
- Display only (no forms that modify the model)
- Clear "not trained yet" state
- Instructions for users on how to generate model

**Why this matters:**
- ✅ Users see current status
- ✅ Clear instructions for first-time setup
- ✅ No confusion between notebook and web status

---

## Deployment Workflow

### Step 1: Run the Notebook
```
1. Open Medledger_rev2.ipynb in Google Colab
2. Mount Google Drive
3. Run all cells (FedAvg training happens here)
4. At the end, the notebook exports artifacts
   - global_model.pt
   - metrics.json
   - export.zip
```

### Step 2: Download Artifacts
```
1. Download export.zip from Colab
2. Extract to your website directory
```

### Step 3: Deploy Artifacts
```
# Copy model
cp global_model.pt → website/models/

# Copy metrics
cp metrics.json → website/logs/
```

### Step 4: Verify on Website
```
1. Go to Admin Dashboard → See model status
2. Go to /model-status → See detailed metrics
3. Refresh page → Shows latest timestamp
```

---

## Healthcare Privacy Considerations

### Why This Design is Suitable for Healthcare

1. **Data Never Leaves Hospitals**
   - Each hospital trains locally with its own data
   - Only model updates (weights) are aggregated
   - The website never sees raw imaging data

2. **Audit Trail**
   - `last_updated` timestamp in metrics.json
   - Git version control on trained models
   - Clear separation: notebook = training, website = reporting

3. **No Live Connections**
   - Website doesn't trigger training
   - No real-time model retraining
   - No exposure of model architecture to web
   - Scheduled/manual training runs in isolated notebook

4. **Secure Deployment**
   - Model stored as static file (no execution in Flask)
   - Metrics are read-only JSON
   - No PyTorch/CUDA dependencies on production server
   - Easier to audit and secure

---

## File Structure After Integration

```
website/
├── app.py                      # Updated with FL routes
├── fl_integration.py           # NEW: Metrics loader utility
├── models/
│   └── global_model.pt        # Exported by notebook
├── logs/
│   └── metrics.json           # Exported by notebook
├── templates/
│   ├── admin.html             # Updated: shows model status
│   ├── model_status.html      # Updated: detailed metrics display
│   ├── hospital.html
│   ├── index.html
│   └── login.html
├── static/
│   └── style.css
├── data/
│   ├── hospital1/
│   ├── hospital2/
│   ├── hospital3/
│   ├── hospital4/
│   └── hospital5/
├── Medledger_rev2.ipynb       # Updated: added export cell
└── README.md
```

---

## Troubleshooting

### Problem: Model Status Shows "Not Trained Yet"
**Solution:**
1. Verify `models/global_model.pt` exists
2. Verify `logs/metrics.json` exists
3. Check JSON format: `python -m json.tool logs/metrics.json`

### Problem: Metrics Show "Unknown"
**Cause:** `metrics.json` is missing or corrupted
**Solution:**
1. Re-run the notebook export cell
2. Download and extract export.zip again
3. Check file permissions

### Problem: Flask App Won't Start
**Cause:** `fl_integration.py` not found or import error
**Solution:**
1. Verify `fl_integration.py` is in the same directory as `app.py`
2. Check Python path: `echo $PYTHONPATH`
3. Verify no syntax errors: `python -m py_compile fl_integration.py`

---

## Future Enhancements

### Possible Extensions (Not Implemented)
1. **Model Versioning**: Track multiple trained models
   ```python
   models/
   ├── global_model_v1.pt
   ├── global_model_v2.pt
   └── metrics_history.json
   ```

2. **Background Training**: (Still respects privacy)
   ```python
   # Notebook runs as scheduled Colab job
   # Website polling checks for new metrics
   ```

3. **Federated Learning Dashboard**:
   ```
   - Round-by-round accuracy curves
   - Per-hospital contribution metrics
   - Convergence plots
   ```

4. **Model Download**: Hospital-specific fine-tuned copies
   ```
   GET /api/model/hospital1
   → Returns trained model for local inference
   ```

---

## Code Comments in Codebase

Search for **"Federated Learning integration point"** throughout the codebase to find all FL-specific code sections:

1. `fl_integration.py`: Metrics loading utility
2. `app.py`: Route integration
3. `admin.html`: Model status display
4. `model_status.html`: Detailed metrics page
5. `Medledger_rev2.ipynb`: Export logic (last cell)

---

## Summary

| Aspect | Notebook | Website |
|--------|----------|---------|
| **Trains Model** | ✓ | ✗ |
| **Uses PyTorch** | ✓ | ✗ |
| **Accesses Data** | ✓ (from hospitals) | ✗ |
| **Displays Metrics** | ✓ (prints) | ✓ (HTML) |
| **Exports Artifacts** | ✓ | ✗ |
| **Reads Artifacts** | ✗ | ✓ |
| **Public Facing** | ✗ (Colab) | ✓ (Web) |
| **Requires GPU** | ✓ | ✗ |

This design ensures:
- **Healthcare Privacy**: Data stays local, only models aggregate
- **Security**: Website can't access raw model (only trained weights)
- **Scalability**: Stateless Flask app can be containerized easily
- **Maintainability**: Clean separation between training and serving
