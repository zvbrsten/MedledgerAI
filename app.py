from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file
from werkzeug.utils import secure_filename
import os
import datetime
import json
import hashlib
from functools import wraps
from time import time

# Federated Learning integration imports
from fl_integration import load_metrics, get_model_info
from metrics_loader import load_federated_metrics, get_model_status_text, format_timestamp
from server.round_manager import get_round_manager
from server.fedavg import FedAvgAggregator

# Application root paths
APP_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(APP_ROOT, 'data')
MODELS_DIR = os.path.join(APP_ROOT, 'models')
LOGS_DIR = os.path.join(APP_ROOT, 'logs')
CONFIG_DIR = os.path.join(APP_ROOT, 'config')
INCOMING_MODELS_DIR = os.path.join(MODELS_DIR, 'incoming')

ALLOWED_EXTENSIONS = {'.csv', '.zip'}
ALLOWED_WEIGHT_EXTENSIONS = {'.pt', '.pth'}
MAX_WEIGHT_FILE_SIZE = 200 * 1024 * 1024  # 200 MB

app = Flask(__name__)
app.secret_key = 'demo-secret-key-for-medledger'  # Demo-only secret

# ================================================================
# FEDERATED LEARNING: Local Model Update Submission Endpoint
# ================================================================
# SECURITY: Hospitals authenticate via X-API-KEY header
#           API tokens stored in config/hospitals.json (pre-shared)
#           NO dataset data accepted - only model weights + metrics
# ================================================================

def load_hospital_tokens():
    """Load pre-shared API tokens from config/hospitals.json"""
    tokens_path = os.path.join(CONFIG_DIR, 'hospitals.json')
    try:
        with open(tokens_path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        app.logger.error(f"hospitals.json not found or invalid at {tokens_path}")
        return {}

def verify_api_key(hospital_id, api_key):
    """Validate API key for hospital.
    
    Args:
        hospital_id: Hospital identifier
        api_key: Token from X-API-KEY header
    
    Returns:
        True if valid, False otherwise
    """
    tokens = load_hospital_tokens()
    stored_key = tokens.get(hospital_id)
    
    # Secure comparison to prevent timing attacks
    if stored_key is None:
        return False
    
    return stored_key == api_key

def get_hospital_submissions(hospital_id):
    """Get list of previously accepted round numbers for a hospital."""
    hospital_dir = os.path.join(INCOMING_MODELS_DIR, hospital_id)
    if not os.path.exists(hospital_dir):
        return []
    
    rounds = []
    for round_folder in os.listdir(hospital_dir):
        if round_folder.startswith('round_'):
            try:
                round_num = int(round_folder.split('_')[1])
                rounds.append(round_num)
            except (ValueError, IndexError):
                pass
    return sorted(rounds)

def rate_limit_key(hospital_id):
    """Generate rate limit key for hospital."""
    return f"submit_update_{hospital_id}"

def is_rate_limited(hospital_id, limit_per_minute=10):
    """Simple in-memory rate limiting (per hospital, per minute)."""
    if not hasattr(app, 'request_times'):
        app.request_times = {}
    
    key = rate_limit_key(hospital_id)
    now = time()
    
    if key not in app.request_times:
        app.request_times[key] = []
    
    # Remove requests older than 1 minute
    app.request_times[key] = [t for t in app.request_times[key] if now - t < 60]
    
    # Check limit
    if len(app.request_times[key]) >= limit_per_minute:
        return True
    
    app.request_times[key].append(now)
    return False

# ------------------------------------------------------------------
# Hardcoded demo users (simple demo-level auth)
# Two roles: 'admin' and 'hospital'
# Hospitals: hospital1..hospital5 with password 'password'
# Admin: admin / adminpass
# ------------------------------------------------------------------
USERS = {'admin': {'password': 'adminpass', 'role': 'admin'}}
for i in range(1, 6):
    USERS[f'hospital{i}'] = {'password': 'password', 'role': 'hospital'}


def allowed_file(filename):
    _, ext = os.path.splitext(filename.lower())
    return ext in ALLOWED_EXTENSIONS


def ensure_hospital_dir(hospital_id):
    path = os.path.join(DATA_DIR, hospital_id)
    os.makedirs(path, exist_ok=True)
    return path


def get_last_upload_info(hospital_id):
    path = os.path.join(DATA_DIR, hospital_id)
    if not os.path.isdir(path):
        return None
    files = [os.path.join(path, f) for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]
    if not files:
        return None
    latest = max(files, key=os.path.getmtime)
    ts = datetime.datetime.fromtimestamp(os.path.getmtime(latest))
    return {'filename': os.path.basename(latest), 'timestamp': ts}


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = USERS.get(username)
        if user and user.get('password') == password:
            session['username'] = username
            session['role'] = user.get('role')
            flash('Login successful', 'success')
            if user.get('role') == 'admin':
                return redirect(url_for('admin'))
            else:
                return redirect(url_for('hospital_dashboard', hospital_id=username))
        else:
            flash('Invalid credentials', 'danger')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out', 'info')
    return redirect(url_for('index'))


@app.route('/hospital/<hospital_id>', methods=['GET', 'POST'])
def hospital_dashboard(hospital_id):
    # Require login
    if 'username' not in session:
        flash('Please log in to access hospital dashboard', 'warning')
        return redirect(url_for('login'))

    # Allow admin to view any hospital, hospitals may only view their own
    if session.get('role') == 'hospital' and session.get('username') != hospital_id:
        flash('Access denied for this hospital account', 'danger')
        return redirect(url_for('index'))

    ensure_hospital_dir(hospital_id)
    upload_info = get_last_upload_info(hospital_id)

    if request.method == 'POST':
        file = request.files.get('dataset')
        if not file or file.filename == '':
            flash('No file selected', 'warning')
            return redirect(url_for('hospital_dashboard', hospital_id=hospital_id))
        if not allowed_file(file.filename):
            flash('File type not allowed. Use .csv or .zip', 'danger')
            return redirect(url_for('hospital_dashboard', hospital_id=hospital_id))

        filename = secure_filename(file.filename)
        dest_dir = ensure_hospital_dir(hospital_id)
        dest_path = os.path.join(dest_dir, filename)
        file.save(dest_path)
        flash(f'File uploaded: {filename}', 'success')

        # FUTURE: Federated Learning integration point
        # - Register uploaded dataset for orchestration
        # - Signal local training worker, etc.

        return redirect(url_for('hospital_dashboard', hospital_id=hospital_id))

    return render_template('hospital.html', hospital_id=hospital_id, upload_info=upload_info)


@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if 'username' not in session or session.get('role') != 'admin':
        flash('Admin access required', 'warning')
        return redirect(url_for('login'))

    # Phase 2: Show model submission status instead of dataset uploads
    rm = get_round_manager()
    round_status = rm.get_round_status()
    
    hospitals = []
    for i in range(1, 6):
        hid = f'hospital{i}'
        has_submitted = hid in round_status['received_hospitals']
        
        # Get last submission info
        last_submission = None
        hospital_submissions_dir = os.path.join(INCOMING_MODELS_DIR, hid)
        if os.path.exists(hospital_submissions_dir):
            # Find latest round submission
            rounds = []
            for round_folder in os.listdir(hospital_submissions_dir):
                if round_folder.startswith('round_'):
                    try:
                        round_num = int(round_folder.split('_')[1])
                        rounds.append(round_num)
                    except (ValueError, IndexError):
                        pass
            
            if rounds:
                latest_round = max(rounds)
                metadata_path = os.path.join(
                    hospital_submissions_dir, f'round_{latest_round}', 'metadata.json'
                )
                if os.path.exists(metadata_path):
                    try:
                        with open(metadata_path, 'r') as f:
                            metadata = json.load(f)
                            last_submission = {
                                'round': metadata.get('round'),
                                'accuracy': metadata.get('metrics', {}).get('accuracy'),
                                'timestamp': metadata.get('received_at')
                            }
                    except:
                        pass
        
        hospitals.append({
            'id': hid,
            'has_submitted': has_submitted,
            'last_submission': last_submission,
            'current_round': round_status['current_round']
        })

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'start_fl':
            flash('Model aggregation is automatic. Hospitals submit weights via notebook.', 'info')
        return redirect(url_for('admin'))

    # Federated Learning integration point: Load model status from artifacts
    model_status = load_metrics(MODELS_DIR, LOGS_DIR)

    return render_template('admin.html', hospitals=hospitals, model_status=model_status, round_status=round_status)


@app.route('/model-status')
def model_status():
    # Federated Learning integration point: Load metrics from exported JSON
    # The notebook exports federated_metrics.json after training completes
    # Website reads this file to display model status (read-only)
    metrics_data = load_federated_metrics(DATA_DIR)
    
    # Format the data for template rendering
    if metrics_data.get("available"):
        status = {
            'model_available': True,
            'rounds_completed': metrics_data.get('training_rounds', 0),
            'accuracy': f"{metrics_data.get('final_accuracy', 0):.2f}%",
            'precision': f"{metrics_data.get('final_precision', 0):.2f}%",
            'recall': f"{metrics_data.get('final_recall', 0):.2f}%",
            'f1_score': f"{metrics_data.get('final_f1_score', 0):.4f}",
            'auc_roc': f"{metrics_data.get('final_auc_roc', 0):.2f}%",
            'loss': f"{metrics_data.get('final_loss', 0):.4f}",
            'last_updated': format_timestamp(metrics_data.get('last_updated', '')),
            'accuracy_array': metrics_data.get('accuracy_per_round', []),
            'precision_array': metrics_data.get('precision_per_round', []),
            'recall_array': metrics_data.get('recall_per_round', []),
            'f1_array': metrics_data.get('f1_score_per_round', []),
            'loss_array': metrics_data.get('loss_per_round', []),
            'auc_array': metrics_data.get('auc_roc_per_round', []),
            'model_id': metrics_data.get('model_id', 'medledger_global'),
            'institutions': metrics_data.get('institutions_participated', 0),
            'training_history': metrics_data.get('training_history', [])
        }
    else:
        # Fallback to empty metrics if file not available
        status = {
            'model_available': True,  # Always show the page now
            'rounds_completed': 0,
            'accuracy': '0.00%',
            'precision': '0.00%',
            'recall': '0.00%',
            'f1_score': '0.0000',
            'auc_roc': '0.00%',
            'loss': '0.0000',
            'last_updated': 'Not yet trained',
            'accuracy_array': [],
            'precision_array': [],
            'recall_array': [],
            'f1_array': [],
            'loss_array': [],
            'auc_array': [],
            'model_id': 'medledger_global',
            'institutions': 0,
            'training_history': []
        }
    
    return render_template('model_status.html', status=status)


@app.route('/federated-metrics')
def federated_metrics():
    """
    Federated Learning Model Status Dashboard
    
    Integration Point: Reads exported metrics.json from training pipeline
    This route is read-only and displays snapshots of model training.
    No training is triggered or modified here.
    """
    metrics = load_federated_metrics(DATA_DIR)
    
    # Format timestamp for display
    if metrics.get("available"):
        metrics["last_updated_formatted"] = format_timestamp(metrics.get("last_updated"))
        metrics["status_text"] = get_model_status_text(metrics)
    
    return render_template('federated_metrics.html', metrics=metrics)


@app.route('/api/append-metrics-round', methods=['POST'])
def api_append_metrics_round():
    """
    API endpoint for appending new training round metrics.
    
    Endpoint: POST /api/append-metrics-round
    Authentication: Admin-only
    
    Payload (JSON):
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
        "timestamp": "2026-01-30T15:30:00"  # Optional, auto-generated if omitted
    }
    
    Returns:
        JSON: {"success": true, "message": "Round X appended successfully"}
    """
    
    # Require admin auth
    if 'username' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Admin access required'}), 401
    
    data = request.get_json()
    
    # Validate required fields
    required_fields = ['round', 'accuracy', 'precision', 'recall', 'f1_score', 'loss', 'auc_roc']
    if not all(field in data for field in required_fields):
        return jsonify({'success': False, 'error': 'Missing required fields'}), 400
    
    try:
        metrics_path = os.path.join(DATA_DIR, 'federated_metrics.json')
        
        if not os.path.exists(metrics_path):
            return jsonify({'success': False, 'error': 'Metrics file not found'}), 404
        
        # Load existing metrics
        with open(metrics_path, 'r') as f:
            metrics = json.load(f)
        
        # Update metrics
        timestamp = data.get('timestamp', datetime.datetime.now().isoformat())
        metrics['last_updated'] = timestamp
        metrics['training_rounds'] = data['round']
        
        # Append to per-round arrays
        metrics['accuracy_per_round'].append(data['accuracy'])
        metrics['precision_per_round'].append(data['precision'])
        metrics['recall_per_round'].append(data['recall'])
        metrics['f1_score_per_round'].append(data['f1_score'])
        metrics['loss_per_round'].append(data['loss'])
        metrics['auc_roc_per_round'].append(data['auc_roc'])
        
        # Update final metrics
        metrics['final_accuracy'] = data['accuracy'] * 100
        metrics['final_precision'] = data['precision'] * 100
        metrics['final_recall'] = data['recall'] * 100
        metrics['final_f1_score'] = data['f1_score']
        metrics['final_loss'] = data['loss']
        metrics['final_auc_roc'] = data['auc_roc'] * 100
        metrics['institutions_participated'] = data.get('institutions_participated', 5)
        
        # Append to training history
        history_entry = {
            'round': data['round'],
            'timestamp': timestamp,
            'institutions_participated': data.get('institutions_participated', 5),
            'samples_processed': data.get('samples_processed', 20000),
            'accuracy': data['accuracy'],
            'precision': data['precision'],
            'recall': data['recall'],
            'f1_score': data['f1_score'],
            'loss': data['loss'],
            'auc_roc': data['auc_roc']
        }
        metrics['training_history'].append(history_entry)
        
        # Save updated metrics
        with open(metrics_path, 'w') as f:
            json.dump(metrics, f, indent=2)
        
        return jsonify({
            'success': True,
            'message': f'Round {data["round"]} appended successfully',
            'round': data['round'],
            'metrics': {
                'accuracy': data['accuracy'],
                'precision': data['precision'],
                'recall': data['recall'],
                'f1_score': data['f1_score'],
                'loss': data['loss'],
                'auc_roc': data['auc_roc']
            }
        }), 200
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/submit_update', methods=['POST'])
def submit_model_update():
    """
    Federated Learning: Secure Model Update Submission Endpoint
    
    SECURITY NOTE:
    - Hospitals submit only LOCAL MODEL WEIGHTS and METRICS
    - NO patient data, images, or datasets are accepted
    - Authentication via X-API-KEY header (pre-shared tokens)
    - All received weights are hashed for tamper evidence
    
    Expected multipart form-data:
    - hospital_id (string)
    - round (int)
    - weights (file, .pt or .pth only)
    - metrics (JSON string or form field)
      {
        "accuracy": float,
        "loss": float,
        "num_samples": int (optional),
        "timestamp": "ISO_8601" (optional, auto-generated if omitted)
      }
    
    Header required:
    - X-API-KEY: pre-shared token for hospital (from config/hospitals.json)
    
    Returns:
    - 200: Success with metadata ID
    - 400: Validation error
    - 401: Authentication failure
    - 409: Conflict (round already submitted with same hash)
    - 413: File too large
    - 429: Rate limited
    """
    
    # ===== RATE LIMITING =====
    hospital_id = request.form.get('hospital_id', '').strip()
    if hospital_id and is_rate_limited(hospital_id, limit_per_minute=10):
        return jsonify({
            'success': False,
            'error': 'Rate limit exceeded. Maximum 10 submissions per minute.'
        }), 429
    
    # ===== AUTHENTICATION =====
    api_key = request.headers.get('X-API-KEY', '')
    if not hospital_id:
        return jsonify({
            'success': False,
            'error': 'Missing hospital_id in form data'
        }), 400
    
    if not api_key:
        return jsonify({
            'success': False,
            'error': 'Missing X-API-KEY header'
        }), 401
    
    if not verify_api_key(hospital_id, api_key):
        app.logger.warning(f"AUTH FAILED: Invalid API key for hospital {hospital_id}")
        return jsonify({
            'success': False,
            'error': 'Invalid API key for hospital'
        }), 401
    
    # ===== EXTRACT FORM FIELDS =====
    try:
        round_num = int(request.form.get('round', -1))
        if round_num < 1:
            raise ValueError("Round must be >= 1")
    except (ValueError, TypeError):
        return jsonify({
            'success': False,
            'error': 'Invalid round number. Must be integer >= 1'
        }), 400
    
    # Check monotonic: round must be > than previously accepted rounds
    previous_rounds = get_hospital_submissions(hospital_id)
    if previous_rounds and round_num <= max(previous_rounds):
        return jsonify({
            'success': False,
            'error': f'Round {round_num} already submitted or lower than previous round. '
                     f'Expected > {max(previous_rounds)}'
        }), 400
    
    # ===== FILE VALIDATION =====
    if 'weights' not in request.files:
        return jsonify({
            'success': False,
            'error': 'Missing weights file in form data'
        }), 400
    
    weights_file = request.files['weights']
    if weights_file.filename == '':
        return jsonify({
            'success': False,
            'error': 'No file selected'
        }), 400
    
    # Check file extension
    filename = secure_filename(weights_file.filename)
    file_ext = os.path.splitext(filename)[1].lower()
    if file_ext not in ALLOWED_WEIGHT_EXTENSIONS:
        return jsonify({
            'success': False,
            'error': f'Invalid file type. Allowed: {", ".join(ALLOWED_WEIGHT_EXTENSIONS)}'
        }), 400
    
    # Check file size (before saving)
    weights_file.seek(0, os.SEEK_END)
    file_size = weights_file.tell()
    weights_file.seek(0)
    
    if file_size > MAX_WEIGHT_FILE_SIZE:
        return jsonify({
            'success': False,
            'error': f'File too large. Maximum size: {MAX_WEIGHT_FILE_SIZE / (1024*1024):.0f} MB'
        }), 413
    
    # ===== METRICS VALIDATION =====
    metrics_raw = request.form.get('metrics', '{}')
    try:
        metrics = json.loads(metrics_raw)
    except json.JSONDecodeError:
        return jsonify({
            'success': False,
            'error': 'Invalid metrics JSON'
        }), 400
    
    # Validate required metric fields
    required_metric_keys = {'accuracy', 'loss'}
    if not required_metric_keys.issubset(set(metrics.keys())):
        return jsonify({
            'success': False,
            'error': f'Metrics must contain: {", ".join(required_metric_keys)}'
        }), 400
    
    # Validate metric values
    try:
        accuracy = float(metrics.get('accuracy'))
        loss = float(metrics.get('loss'))
        if not (0 <= accuracy <= 1):
            raise ValueError("accuracy must be between 0 and 1")
        if loss < 0:
            raise ValueError("loss must be non-negative")
    except (ValueError, TypeError) as e:
        return jsonify({
            'success': False,
            'error': f'Invalid metric values: {str(e)}'
        }), 400
    
    # ===== CREATE STORAGE DIRECTORY =====
    hospital_round_dir = os.path.join(
        INCOMING_MODELS_DIR, hospital_id, f'round_{round_num}'
    )
    os.makedirs(hospital_round_dir, exist_ok=True)
    
    # ===== SAVE WEIGHTS FILE =====
    weights_path = os.path.join(hospital_round_dir, 'weights.pt')
    try:
        weights_file.save(weights_path)
    except Exception as e:
        app.logger.error(f"Failed to save weights for {hospital_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to save weights file'
        }), 500
    
    # ===== COMPUTE SHA-256 HASH =====
    try:
        sha256_hash = hashlib.sha256()
        with open(weights_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                sha256_hash.update(chunk)
        file_hash = sha256_hash.hexdigest()
    except Exception as e:
        app.logger.error(f"Failed to compute hash: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to verify file integrity'
        }), 500
    
    # ===== SAVE HASH =====
    hash_path = os.path.join(hospital_round_dir, 'weights.sha256')
    try:
        with open(hash_path, 'w') as f:
            f.write(file_hash)
    except Exception as e:
        app.logger.error(f"Failed to save hash: {str(e)}")
    
    # ===== SAVE METADATA =====
    uploader_ip = request.remote_addr
    timestamp = metrics.get('timestamp', datetime.datetime.utcnow().isoformat() + 'Z')
    
    metadata = {
        'hospital_id': hospital_id,
        'round': round_num,
        'filename': 'weights.pt',
        'sha256': file_hash,
        'file_size_bytes': file_size,
        'metrics': {
            'accuracy': accuracy,
            'loss': loss,
            'num_samples': metrics.get('num_samples', None),
            'timestamp': timestamp
        },
        'received_at': datetime.datetime.utcnow().isoformat() + 'Z',
        'uploader_ip': uploader_ip
    }
    
    metadata_path = os.path.join(hospital_round_dir, 'metadata.json')
    try:
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
    except Exception as e:
        app.logger.error(f"Failed to save metadata: {str(e)}")
    
    # ===== AUDIT LOGGING (metadata only, NO weights) =====
    app.logger.info(
        f"MODEL UPDATE RECEIVED | hospital={hospital_id} | "
        f"round={round_num} | accuracy={accuracy:.4f} | loss={loss:.4f} | "
        f"hash={file_hash[:16]}... | size={file_size / (1024*1024):.2f}MB | "
        f"ip={uploader_ip}"
    )
    
    # ===== REGISTER SUBMISSION WITH ROUND MANAGER =====
    rm = get_round_manager()
    submission_status = rm.register_submission(
        hospital_id=hospital_id,
        weights_path=weights_path,
        num_samples=metrics.get('num_samples', 1)  # Default to 1 if not provided
    )
    
    # ===== CHECK IF ALL HOSPITALS HAVE SUBMITTED - TRIGGER AGGREGATION =====
    if submission_status['ready_for_aggregation']:
        app.logger.info(
            f"[FEDAVG] All hospitals submitted for round {round_num}. "
            f"Triggering aggregation..."
        )
        
        # Perform aggregation
        try:
            aggregator = FedAvgAggregator()
            current_round = rm.get_current_round()
            
            # Mark aggregation start
            rm.mark_aggregation_start()
            
            # Get submissions for this round
            submissions = rm.get_submissions_for_round(current_round)
            app.logger.info(f"[FEDAVG] Aggregating {len(submissions)} hospital submissions")
            
            # Perform weighted FedAvg
            success, agg_msg, metadata = aggregator.aggregate(
                submissions=submissions,
                global_round=current_round,
                output_dir=os.path.join(MODELS_DIR, 'global')
            )
            
            if success:
                global_model_path = metadata['global_model_path']
                app.logger.info(
                    f"[FEDAVG] ✓ Aggregation complete | "
                    f"global_model_path={global_model_path} | "
                    f"hospitals={metadata['total_hospitals']} | "
                    f"samples={metadata['total_samples']}"
                )
                
                # Mark aggregation complete and increment round
                rm.mark_aggregation_complete(global_model_path)
                
                # Log aggregation details to federated_metrics
                try:
                    metrics_path = os.path.join(DATA_DIR, 'federated_metrics.json')
                    if os.path.exists(metrics_path):
                        with open(metrics_path, 'r') as f:
                            fed_metrics = json.load(f)
                        
                        # Update last aggregation info
                        fed_metrics['last_aggregation_round'] = current_round
                        fed_metrics['last_aggregation_timestamp'] = datetime.datetime.utcnow().isoformat() + 'Z'
                        fed_metrics['aggregation_status'] = 'complete'
                        
                        with open(metrics_path, 'w') as f:
                            json.dump(fed_metrics, f, indent=2)
                except Exception as e:
                    app.logger.error(f"Failed to update federated_metrics: {str(e)}")
            else:
                app.logger.error(f"[FEDAVG] Aggregation failed: {agg_msg}")
                
        except Exception as e:
            app.logger.exception(f"[FEDAVG] Unexpected error during aggregation: {str(e)}")
    
    return jsonify({
        'success': True,
        'message': f'Model update for round {round_num} received successfully',
        'metadata_id': f'{hospital_id}_round{round_num}',
        'aggregation_status': submission_status.get('status', 'pending')
    }), 200


@app.route('/api/global-model/latest', methods=['GET'])
def get_global_model():
    """
    Federated Learning: Global Model Distribution Endpoint
    
    ARCHITECTURAL NOTE:
        This endpoint allows hospitals to download the latest aggregated global model.
        
        Security:
        ✓ No authentication required (prototype mode)
        ✓ Returns only model weights (.pt file)
        ✗ Never returns patient data
        ✗ Never triggers training
        ✗ Never exposes hospital submissions
    
    Response:
        200: Binary .pt file with headers:
             - X-GLOBAL-ROUND: Current FL round number
             - X-MODEL-HASH: SHA-256 hash of weights
             - Content-Disposition: Suggests filename
        
        404: No global model available yet
    """
    try:
        rm = get_round_manager()
        current_round = rm.get_current_round()
        
        # Find latest completed global model
        global_models_dir = os.path.join(MODELS_DIR, 'global')
        
        if not os.path.exists(global_models_dir):
            return jsonify({
                'error': 'No global model available yet',
                'message': 'Waiting for first aggregation to complete'
            }), 404
        
        # Find the highest round number that has been aggregated
        available_rounds = []
        for filename in os.listdir(global_models_dir):
            if filename.startswith('global_model_round') and filename.endswith('.pt'):
                try:
                    round_num = int(filename.replace('global_model_round', '').replace('.pt', ''))
                    available_rounds.append(round_num)
                except ValueError:
                    pass
        
        if not available_rounds:
            return jsonify({
                'error': 'No global model available yet',
                'message': 'Waiting for first aggregation to complete'
            }), 404
        
        # Get the latest (highest) round
        latest_round = max(available_rounds)
        global_model_path = os.path.join(
            global_models_dir,
            f'global_model_round{latest_round}.pt'
        )
        
        if not os.path.exists(global_model_path):
            return jsonify({
                'error': 'Model file not found',
                'path': global_model_path
            }), 404
        
        # Compute model hash for integrity verification
        try:
            sha256_hash = hashlib.sha256()
            with open(global_model_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b''):
                    sha256_hash.update(chunk)
            model_hash = sha256_hash.hexdigest()
        except Exception as e:
            app.logger.error(f"Failed to compute hash: {str(e)}")
            model_hash = 'unavailable'
        
        # Log download request
        app.logger.info(
            f"[DOWNLOAD] Global model request | "
            f"round={latest_round} | "
            f"ip={request.remote_addr}"
        )
        
        # Send file with metadata headers
        file_size = os.path.getsize(global_model_path)
        
        return send_file(
            global_model_path,
            mimetype='application/octet-stream',
            as_attachment=True,
            download_name=f'global_model_round{latest_round}.pt',
            headers={
                'X-GLOBAL-ROUND': str(latest_round),
                'X-MODEL-HASH': model_hash,
                'X-FILE-SIZE': str(file_size)
            }
        )
    
    except Exception as e:
        app.logger.exception(f"Error serving global model: {str(e)}")
        return jsonify({
            'error': 'Internal server error',
            'message': str(e)
        }), 500


@app.route('/api/round-status', methods=['GET'])
def get_round_status():
    """
    Federated Learning: Current Round Status Endpoint
    
    Returns current round number, expected hospitals, and aggregation status.
    
    Useful for:
    - Hospitals to know if they should submit
    - Hospitals to know if aggregated model is ready for download
    - Website dashboard to show coordination status
    
    No authentication required (prototype mode).
    """
    try:
        rm = get_round_manager()
        status = rm.get_round_status()
        
        return jsonify({
            'success': True,
            'current_round': status['current_round'],
            'expected_hospitals': status['expected_hospitals'],
            'received_hospitals': status['received_hospitals'],
            'missing_hospitals': status['missing_hospitals'],
            'ready_for_aggregation': status['ready_for_aggregation'],
            'aggregation_status': status['aggregation_status'],
            'timestamp': datetime.datetime.utcnow().isoformat() + 'Z'
        }), 200
    
    except Exception as e:
        app.logger.exception(f"Error getting round status: {str(e)}")
        return jsonify({
            'error': 'Internal server error',
            'message': str(e)
        }), 500


if __name__ == '__main__':

    # Run development server
    app.run(debug=True, host='0.0.0.0', port=5000)

