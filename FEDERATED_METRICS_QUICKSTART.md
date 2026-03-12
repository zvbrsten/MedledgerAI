# Federated Metrics Integration — Quick Start

## For Reviewers

### What This Is
A read-only dashboard displaying federated learning training metrics exported from a Jupyter notebook.

### How to Use
1. **Run the website:** `python app.py` (already running at http://127.0.0.1:5000)
2. **Login:** admin / adminpass
3. **View metrics:** Click "Federated Training Status" on the admin page
4. **See charts:** View accuracy and loss progression across training rounds

### Key File
- **Export source:** `Medledger_rev2.ipynb` (Cell 17)
- **Artifact:** `/data/federated_metrics.json`
- **Dashboard:** `/federated-metrics` route

---

## For Developers

### Adding Metrics to the Website

#### Step 1: Notebook Exports
The notebook creates a JSON file:
```python
# In Medledger_rev2.ipynb (Cell 17)
metrics = {
    "model_id": "medledger_global_v1",
    "last_updated": datetime.now().isoformat(),
    "institutions_participated": 5,
    "training_rounds": rounds,
    "accuracy_per_round": [0.71, 0.74, ...],
    "loss_per_round": [0.68, 0.61, ...],
    "final_accuracy": 89.50,
    "model_status": "available"
}
# Saves to: export/federated_metrics.json
```

#### Step 2: Deploy to Website
```bash
# Copy metrics to data directory
cp export/federated_metrics.json /path/to/website/data/
```

#### Step 3: Website Displays
```
GET /federated-metrics
    → Flask calls load_federated_metrics()
    → Reads JSON from /data/
    → Renders federated_metrics.html with charts
```

### Code Overview

**`metrics_loader.py`** — Read-only utilities
```python
load_federated_metrics(data_dir)     # Load JSON, validate, return dict
get_model_status_text(metrics)       # Format status for display
format_timestamp(iso_string)         # Convert ISO → readable
```

**`app.py`** — Flask route
```python
@app.route('/federated-metrics')
def federated_metrics():
    metrics = load_federated_metrics(DATA_DIR)
    return render_template('federated_metrics.html', metrics=metrics)
```

**`templates/federated_metrics.html`** — Dashboard
- Displays model status panel
- Renders accuracy chart (Chart.js)
- Renders loss chart (Chart.js)
- Handles missing metrics gracefully

---

## Sample Metrics File

To test without running the notebook, create `/data/federated_metrics.json`:

```json
{
  "model_id": "medledger_global_v1",
  "last_updated": "2026-01-29T14:32:00",
  "institutions_participated": 5,
  "training_rounds": 10,
  "accuracy_per_round": [0.71, 0.734, 0.762, 0.785, 0.812, 0.834, 0.851, 0.868, 0.882, 0.895],
  "loss_per_round": [0.68, 0.61, 0.55, 0.49, 0.43, 0.385, 0.342, 0.305, 0.272, 0.245],
  "final_accuracy": 89.50,
  "model_status": "available"
}
```

Then visit: http://127.0.0.1:5000/federated-metrics

---

## Design Principles

| Principle | Rationale |
|-----------|-----------|
| **Read-Only** | Website never triggers training |
| **JSON Artifacts** | Language-agnostic data format |
| **No PyTorch in Flask** | Lightweight, secure deployment |
| **Graceful Degradation** | Missing metrics show "Not Available" |
| **Chart Visualization** | Intuitive training progress display |

---

## Files Created/Modified

| File | Purpose |
|------|---------|
| `metrics_loader.py` | **NEW** — Read-only JSON loader |
| `templates/federated_metrics.html` | **NEW** — Dashboard template |
| `Medledger_rev2.ipynb` | **MODIFIED** — Enhanced export cell |
| `app.py` | **MODIFIED** — Added `/federated-metrics` route |
| `templates/admin.html` | **MODIFIED** — Added link to metrics page |
| `data/federated_metrics.json` | **NEW** — Sample metrics for testing |

---

## Testing Checklist

- [ ] Website loads without errors
- [ ] Admin page shows "Federated Training Status" link
- [ ] `/federated-metrics` route displays dashboard
- [ ] Charts render with sample data
- [ ] Timestamp displays correctly
- [ ] Missing metrics show "Not Available" state
- [ ] No PyTorch imports in Flask code

---

## Phase-1 Scope

✅ **Included:**
- Read-only metrics display
- Training progress charts
- Artifact-based integration
- Graceful error handling

❌ **Not Included (Phase-2 Future):**
- Model update requests
- Artifact replacement workflows
- Manual approval flows
- Automated retraining triggers
