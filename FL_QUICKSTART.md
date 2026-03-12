# Quick Start: FL Integration Setup

## Prerequisites
- Python 3.8+
- Flask installed
- Notebook run completed (with export.zip generated)

## Step-by-Step Setup

### 1. Extract Exported Artifacts
```bash
# Download export.zip from Colab notebook output

# Extract to website directories
unzip export.zip

# Copy exported files
cp export/global_model.pt ./models/
cp export/metrics.json ./logs/
```

### 2. Verify Files Exist
```bash
# Check model
ls -lh models/global_model.pt

# Check metrics
cat logs/metrics.json
```

Expected metrics.json format:
```json
{
  "rounds_completed": 5,
  "accuracy": 95.32,
  "loss": null,
  "last_updated": "2025-01-29T14:32:10.123456"
}
```

### 3. Test Flask Integration
```bash
# Run Flask app
python app.py

# Visit in browser
# Admin: http://localhost:5000/admin
# Model Status: http://localhost:5000/model-status
```

### 4. Verify Integration Points
Check that you see:
- ✓ Admin dashboard shows "Model Available"
- ✓ Model status page shows accuracy and rounds
- ✓ Timestamp matches notebook run time

---

## Common Integration Errors

### ImportError: No module named 'fl_integration'
**Fix:** Ensure `fl_integration.py` is in the same directory as `app.py`
```bash
ls -la fl_integration.py app.py
```

### FileNotFoundError: models/global_model.pt
**Fix:** Make sure export artifacts are in correct location
```bash
# Create directories if needed
mkdir -p models logs

# Copy files
cp export/global_model.pt models/
cp export/metrics.json logs/
```

### JSON parsing error in metrics.json
**Fix:** Verify JSON is valid
```bash
python -m json.tool logs/metrics.json
```

---

## What to Expect

### Before Training
- Model Status Page: "No Model Trained Yet"
- Admin Dashboard: Shows "No model trained yet"

### After Training (After export.zip extracted)
- Model Status Page: Shows all metrics
  - Rounds Completed: 5
  - Test Accuracy: 95.32%
  - Last Updated: [timestamp]
- Admin Dashboard: Shows "✓ Model Available" with metrics

---

## Testing Checklist

- [ ] `models/global_model.pt` file exists and is not empty
- [ ] `logs/metrics.json` file exists and is valid JSON
- [ ] Flask app starts without import errors
- [ ] Admin page loads and shows model status
- [ ] Model Status page loads and displays metrics
- [ ] Refreshing page shows same data (file-based, not cached)
- [ ] Metrics match what was printed in notebook

---

## Deployment Notes

### For Production
1. Use environment variables for directory paths
2. Add file existence validation on app startup
3. Consider read-only file permissions on models/
4. Use proper logging instead of print()

### For Docker
Include these in Dockerfile:
```dockerfile
COPY models/ /app/models/
COPY logs/ /app/logs/
# Ensure directories are readable
RUN chmod 755 /app/models /app/logs
```

### Monitoring
- Watch `logs/metrics.json` modification time
- Alert if metrics become stale (e.g., > 7 days)
- Consider backing up models/ directory regularly
