# Deployment & Verification Guide

## Pre-Deployment Checklist

### Environment Setup
- [ ] Python 3.8+ installed
- [ ] Flask installed: `pip install flask`
- [ ] All required directories exist: `models/`, `logs/`, `data/`, `templates/`, `static/`
- [ ] Virtual environment activated (if using one)

### File Verification
- [ ] `app.py` contains `from fl_integration import load_metrics`
- [ ] `fl_integration.py` exists in root directory (same as app.py)
- [ ] `templates/admin.html` updated with model status section
- [ ] `templates/model_status.html` updated with detailed display
- [ ] `Medledger_rev2.ipynb` has export cell added (cell 17)

### Artifacts from Notebook
- [ ] Notebook executed in Google Colab successfully
- [ ] `export/` directory created with artifacts
- [ ] `export/global_model.pt` created (file size > 50MB typical)
- [ ] `export/metrics.json` created (valid JSON format)
- [ ] `export.zip` created successfully

---

## Deployment Steps

### Step 1: Extract Notebook Artifacts
```bash
# Download export.zip from Colab notebook output window

# Extract to current directory
unzip export.zip

# Verify contents
ls -la export/
# Should show:
# - global_model.pt
# - metrics.json
```

### Step 2: Deploy to Website Directory
```bash
# Copy model artifact
cp export/global_model.pt ./models/global_model.pt

# Copy metrics artifact
cp export/metrics.json ./logs/metrics.json

# Verify placement
ls -la models/global_model.pt
ls -la logs/metrics.json
```

### Step 3: Verify JSON Format
```bash
# Validate metrics.json
python -m json.tool logs/metrics.json

# Expected output:
# {
#   "rounds_completed": <integer>,
#   "accuracy": <float>,
#   "loss": null,
#   "last_updated": "<ISO timestamp>"
# }
```

### Step 4: Test Flask App Locally
```bash
# Run Flask development server
python app.py

# Expected output:
# WARNING: This is a development server. Do not use in production.
# Running on http://127.0.0.1:5000/
```

### Step 5: Verify Web Interface

#### 5a. Login
- [ ] Visit: `http://localhost:5000/`
- [ ] Click "Login"
- [ ] Use credentials:
  - Username: `admin`
  - Password: `adminpass`

#### 5b. Admin Dashboard
- [ ] Visit: `http://localhost:5000/admin`
- [ ] Verify: "✓ Model Available" appears
- [ ] Check values match notebook output:
  - Rounds Completed
  - Test Accuracy
  - Last Updated timestamp

#### 5c. Model Status Page
- [ ] Click "Model Status" button (or visit `/model-status`)
- [ ] Verify: "✓ Model Trained and Available" shows
- [ ] Verify table displays:
  - Rounds Completed
  - Test Accuracy
  - Last Updated
- [ ] Verify explanatory text about FedAvg appears

### Step 6: Refresh and Validate
```bash
# Refresh pages multiple times
# Verify same data appears each time (no caching issues)
# Verify no errors in Flask terminal output
```

### Step 7: Check Logs for Errors
```bash
# While Flask is running, check for errors
# Terminal should show:
# GET /admin — successful responses
# GET /model-status — successful responses
# GET /static/* — static file requests

# Watch for any errors like:
# - FileNotFoundError
# - JSONDecodeError
# - ImportError
```

---

## Troubleshooting

### Issue: "No module named 'fl_integration'"
**Symptoms:** Flask crashes when visiting /admin or /model-status

**Solutions:**
1. Verify file location:
   ```bash
   ls -la fl_integration.py app.py
   # Both must be in same directory
   ```

2. Check Python path:
   ```bash
   python -c "import fl_integration; print('OK')"
   ```

3. Look for syntax errors:
   ```bash
   python -m py_compile fl_integration.py
   ```

### Issue: "metrics.json not found" - Model shows "Not trained yet"
**Symptoms:** Admin page shows "No model trained yet" even though you extracted

**Solutions:**
1. Verify file exists:
   ```bash
   ls -la logs/metrics.json
   # Should exist and show size > 100 bytes
   ```

2. Verify JSON is valid:
   ```bash
   python -m json.tool logs/metrics.json
   # Should print valid JSON
   ```

3. Check file permissions:
   ```bash
   # On Unix/Linux:
   chmod 644 logs/metrics.json
   # On Windows: Right-click → Properties → Security
   ```

### Issue: "global_model.pt not found" - Wrong accuracy displayed
**Symptoms:** Metrics show but file size different from expected

**Solutions:**
1. Verify model file:
   ```bash
   ls -lh models/global_model.pt
   # Should be > 50MB (typical ResNet18)
   ```

2. Verify it's the right file:
   ```bash
   file models/global_model.pt
   # Should indicate it's a data file (not corrupted)
   ```

3. Check it's not truncated:
   ```bash
   # File size should match export version
   ls -la export/global_model.pt models/global_model.pt
   # Sizes should be identical
   ```

### Issue: Flask shows "ERR_CONNECTION_REFUSED"
**Symptoms:** Browser can't connect to localhost:5000

**Solutions:**
1. Check Flask is running:
   ```bash
   # Terminal should show: "Running on http://127.0.0.1:5000"
   # If not, re-run: python app.py
   ```

2. Verify port 5000 is available:
   ```bash
   # On Unix/Linux:
   lsof -i :5000
   
   # On Windows (PowerShell):
   netstat -ano | findstr :5000
   
   # If port is in use, modify app.py:
   # app.run(debug=True, port=5001)
   ```

3. Verify no firewall blocking:
   - Check local firewall settings
   - Try: `http://127.0.0.1:5000` instead of `localhost:5000`

### Issue: Login not working
**Symptoms:** "Invalid credentials" even with correct password

**Solutions:**
1. Verify credentials in app.py (lines 20-23):
   ```python
   # Admin login
   username: admin
   password: adminpass
   
   # Hospital login (example)
   username: hospital1
   password: password
   ```

2. Check cookies:
   - Clear browser cookies: Ctrl+Shift+Delete
   - Restart browser
   - Try login again

---

## Production Deployment

### Docker Deployment
```dockerfile
FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Ensure artifact directories exist and are readable
RUN mkdir -p models logs && chmod 755 models logs

EXPOSE 5000

CMD ["python", "app.py"]
```

**Build & Run:**
```bash
docker build -t medledger-ai .
docker run -p 5000:5000 -v $(pwd)/models:/app/models -v $(pwd)/logs:/app/logs medledger-ai
```

### Environment Variables
```bash
# In production, use environment variables instead of hardcoding:
# export FLASK_ENV=production
# export FLASK_SECRET_KEY=<secure-random-key>
# export MODELS_DIR=/path/to/models
# export LOGS_DIR=/path/to/logs
```

### Nginx Configuration (Reverse Proxy)
```nginx
server {
    listen 80;
    server_name medledger.example.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Protect model and logs directories (optional)
    location /models/ {
        deny all;
    }

    location /logs/ {
        deny all;
    }
}
```

### Security Considerations
- [ ] Change `app.secret_key` from demo value
- [ ] Use HTTPS in production (SSL certificates)
- [ ] Restrict file permissions: `chmod 600 models/global_model.pt`
- [ ] Use environment variables for configuration
- [ ] Enable Flask CSRF protection
- [ ] Set up logging and monitoring
- [ ] Regular backups of models/ and logs/

---

## Post-Deployment Validation

### Automated Test Script
Create `test_integration.py`:
```python
import os
import json
import requests

BASE_URL = "http://localhost:5000"

def test_metrics_exist():
    """Test that metrics.json exists and is valid"""
    assert os.path.isfile("logs/metrics.json"), "metrics.json missing"
    
    with open("logs/metrics.json") as f:
        metrics = json.load(f)
    
    assert "rounds_completed" in metrics
    assert "accuracy" in metrics
    assert "last_updated" in metrics
    print("✓ Metrics file valid")

def test_model_exists():
    """Test that global_model.pt exists"""
    assert os.path.isfile("models/global_model.pt"), "global_model.pt missing"
    assert os.path.getsize("models/global_model.pt") > 1000000, "Model file too small"
    print("✓ Model file exists")

def test_admin_page():
    """Test admin page loads and shows status"""
    session = requests.Session()
    
    # Login
    r = session.post(f"{BASE_URL}/login", data={
        "username": "admin",
        "password": "adminpass"
    })
    assert r.status_code == 302, "Login failed"
    
    # Visit admin page
    r = session.get(f"{BASE_URL}/admin")
    assert r.status_code == 200, "Admin page failed"
    assert "Model Available" in r.text or "No model trained yet" in r.text
    print("✓ Admin page loads")

def test_model_status_page():
    """Test model status page loads"""
    r = requests.get(f"{BASE_URL}/model-status")
    assert r.status_code == 200, "Model status page failed"
    assert "Rounds Completed" in r.text or "No Model Trained Yet" in r.text
    print("✓ Model status page loads")

if __name__ == "__main__":
    test_metrics_exist()
    test_model_exists()
    test_admin_page()
    test_model_status_page()
    print("\n✅ All integration tests passed!")
```

**Run:**
```bash
# Install requests if needed
pip install requests

# Run tests
python test_integration.py
```

---

## Monitoring

### Health Check Endpoint (Optional Enhancement)
```python
@app.route('/health')
def health():
    """Simple health check endpoint"""
    status = load_metrics(MODELS_DIR, LOGS_DIR)
    return {
        "status": "healthy",
        "model_available": status["model_available"],
        "metrics_loaded": status["accuracy"] != "Not trained yet"
    }
```

### Logging the Model Status
```python
import logging

logger = logging.getLogger(__name__)

def admin():
    # ... existing code ...
    model_status = load_metrics(MODELS_DIR, LOGS_DIR)
    logger.info(f"Model available: {model_status['model_available']}")
    logger.info(f"Accuracy: {model_status['accuracy']}")
    # ... rest of function ...
```

---

## Summary

✅ **Integration is complete and ready to deploy**

Files modified:
- `app.py` - Added FL integration
- `templates/admin.html` - Updated UI
- `templates/model_status.html` - Updated UI

Files created:
- `fl_integration.py` - Metrics loader
- Documentation files

Follow the checklist above to verify integration, then deploy to production following the security guidelines.

The website now correctly:
- ✅ Displays model training status
- ✅ Shows accuracy and rounds completed
- ✅ Handles missing model gracefully
- ✅ Keeps all ML logic separate from web app
- ✅ Maintains healthcare privacy design
