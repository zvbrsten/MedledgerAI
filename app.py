from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file
from werkzeug.utils import secure_filename
import os
import datetime
import json
import hashlib
import hmac
from functools import wraps
from time import time

# Federated Learning integration imports
from fl_integration import load_metrics, get_model_info
from metrics_loader import load_federated_metrics, get_model_status_text, format_timestamp
from server.round_manager import get_round_manager
from server.fedavg import FedAvgAggregator

# ── BLOCKCHAIN HOOK (Phase 2) ────────────────────────────────────────────────
from blockchain_bridge import log_submission_event, log_aggregation_event, log_login_event
# ────────────────────────────────────────────────────────────────────────────

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

# ── HOSPITAL IDs ─────────────────────────────────────────────────────────────
# Canonical format: hospital_1, hospital_2, ... hospital_5 (WITH underscore)
# Used everywhere: config/hospitals.json, round_manager, admin dashboard
ALL_HOSPITAL_IDS = [f'hospital_{i}' for i in range(1, 6)]
# ─────────────────────────────────────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'medledger-demo-secret-change-in-prod')


# ============================================================================
# SECURITY HELPERS
# ============================================================================

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
    """
    Validate API key for hospital using timing-safe comparison.
    Using hmac.compare_digest prevents timing attacks.
    """
    tokens = load_hospital_tokens()
    stored_key = tokens.get(hospital_id)
    if stored_key is None:
        return False
    # timing-safe comparison
    return hmac.compare_digest(str(stored_key), str(api_key))


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


def is_rate_limited(hospital_id, limit_per_minute=10):
    """Simple in-memory rate limiting (per hospital, per minute)."""
    if not hasattr(app, 'request_times'):
        app.request_times = {}
    key = f"submit_update_{hospital_id}"
    now = time()
    if key not in app.request_times:
        app.request_times[key] = []
    app.request_times[key] = [t for t in app.request_times[key] if now - t < 60]
    if len(app.request_times[key]) >= limit_per_minute:
        return True
    app.request_times[key].append(now)
    return False


# ============================================================================
# DEMO AUTH  (hardcoded — demo only, NOT production)
# Login: hospital_1 / password  ...  hospital_5 / password
#        admin / adminpass
# ============================================================================
USERS = {'admin': {'password': 'adminpass', 'role': 'admin'}}
for _i in range(1, 6):
    USERS[f'hospital_{_i}'] = {'password': 'password', 'role': 'hospital'}


def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if 'username' not in session:
                flash('Please log in first.', 'warning')
                return redirect(url_for('login'))
            if role and session.get('role') != role:
                flash('Access denied.', 'danger')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return wrapped
    return decorator


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
    files = [os.path.join(path, f) for f in os.listdir(path)
             if os.path.isfile(os.path.join(path, f))]
    if not files:
        return None
    latest = max(files, key=os.path.getmtime)
    ts = datetime.datetime.fromtimestamp(os.path.getmtime(latest))
    return {'filename': os.path.basename(latest), 'timestamp': ts}


# ============================================================================
# POST-FEDAVG: Update federated_metrics.json with REAL values from submissions
# ============================================================================

def update_federated_metrics_after_aggregation(current_round, submissions_metadata):
    """
    After FedAvg completes, harvest real accuracy/loss from each hospital's
    metadata.json and write a new round entry into federated_metrics.json.

    Args:
        current_round: The round that just completed
        submissions_metadata: List of dicts from each hospital's metadata.json
    """
    metrics_path = os.path.join(DATA_DIR, 'federated_metrics.json')

    try:
        # Load or create base structure
        if os.path.exists(metrics_path):
            with open(metrics_path, 'r') as f:
                fed_metrics = json.load(f)
        else:
            fed_metrics = {
                "model_id": "medledger_global_v1",
                "last_updated": "",
                "institutions_participated": 5,
                "training_rounds": 0,
                "accuracy_per_round": [],
                "precision_per_round": [],
                "recall_per_round": [],
                "f1_score_per_round": [],
                "loss_per_round": [],
                "auc_roc_per_round": [],
                "training_history": []
            }

        # Compute weighted-average metrics across all hospital submissions
        total_samples = sum(m.get('num_samples', 1) for m in submissions_metadata)
        if total_samples == 0:
            total_samples = len(submissions_metadata)

        avg_accuracy = sum(
            m.get('accuracy', 0) * m.get('num_samples', 1)
            for m in submissions_metadata
        ) / total_samples

        avg_loss = sum(
            m.get('loss', 0) * m.get('num_samples', 1)
            for m in submissions_metadata
        ) / total_samples

        # Use accuracy as proxy for precision/recall/f1 if not provided
        # (hospitals may not submit all metrics)
        avg_precision = sum(
            m.get('precision', m.get('accuracy', 0)) * m.get('num_samples', 1)
            for m in submissions_metadata
        ) / total_samples

        avg_recall = sum(
            m.get('recall', m.get('accuracy', 0)) * m.get('num_samples', 1)
            for m in submissions_metadata
        ) / total_samples

        avg_f1 = sum(
            m.get('f1_score', m.get('accuracy', 0)) * m.get('num_samples', 1)
            for m in submissions_metadata
        ) / total_samples

        avg_auc = sum(
            m.get('auc_roc', m.get('accuracy', 0)) * m.get('num_samples', 1)
            for m in submissions_metadata
        ) / total_samples

        timestamp = datetime.datetime.utcnow().isoformat()

        # Append to per-round arrays
        fed_metrics['accuracy_per_round'].append(round(avg_accuracy, 4))
        fed_metrics['precision_per_round'].append(round(avg_precision, 4))
        fed_metrics['recall_per_round'].append(round(avg_recall, 4))
        fed_metrics['f1_score_per_round'].append(round(avg_f1, 4))
        fed_metrics['loss_per_round'].append(round(avg_loss, 4))
        fed_metrics['auc_roc_per_round'].append(round(avg_auc, 4))

        # Update final/current values
        fed_metrics['training_rounds'] = current_round
        fed_metrics['last_updated'] = timestamp
        fed_metrics['final_accuracy'] = round(avg_accuracy * 100, 2)
        fed_metrics['final_precision'] = round(avg_precision * 100, 2)
        fed_metrics['final_recall'] = round(avg_recall * 100, 2)
        fed_metrics['final_f1_score'] = round(avg_f1, 4)
        fed_metrics['final_loss'] = round(avg_loss, 4)
        fed_metrics['final_auc_roc'] = round(avg_auc * 100, 2)
        fed_metrics['model_status'] = 'available'
        fed_metrics['institutions_participated'] = len(submissions_metadata)

        # Add history entry
        fed_metrics['training_history'].append({
            "round": current_round,
            "timestamp": timestamp,
            "institutions_participated": len(submissions_metadata),
            "samples_processed": total_samples,
            "accuracy": round(avg_accuracy, 4),
            "precision": round(avg_precision, 4),
            "recall": round(avg_recall, 4),
            "f1_score": round(avg_f1, 4),
            "loss": round(avg_loss, 4),
            "auc_roc": round(avg_auc, 4)
        })

        with open(metrics_path, 'w') as f:
            json.dump(fed_metrics, f, indent=2)

        app.logger.info(
            f"[METRICS] Updated federated_metrics.json for round {current_round} "
            f"| accuracy={avg_accuracy:.4f} | loss={avg_loss:.4f}"
        )

    except Exception as e:
        app.logger.error(f"[METRICS] Failed to update federated_metrics: {str(e)}")


def collect_round_metadata(current_round):
    """
    Collect all hospital metadata.json files for a completed round.
    Returns list of metric dicts, one per hospital.
    """
    metadata_list = []
    for hospital_id in ALL_HOSPITAL_IDS:
        metadata_path = os.path.join(
            INCOMING_MODELS_DIR, hospital_id, f'round_{current_round}', 'metadata.json'
        )
        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, 'r') as f:
                    md = json.load(f)
                    metrics = md.get('metrics', {})
                    metrics['num_samples'] = metrics.get('num_samples', 1)
                    # Preserve dp_info at top level for research dashboard
                    if 'dp_info' not in metrics and 'dp_info' in md.get('metrics', {}):
                        metrics['dp_info'] = md['metrics']['dp_info']
                    metadata_list.append(metrics)
            except Exception:
                pass
    return metadata_list


# ============================================================================
# PAGE ROUTES
# ============================================================================

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = USERS.get(username)
        if user and user.get('password') == password:
            session['username'] = username
            session['role'] = user.get('role')
            flash('Login successful', 'success')

            # ── BLOCKCHAIN HOOK ──────────────────────────────────────────────
            try:
                log_login_event(username)
            except Exception as e:
                app.logger.warning(f"Blockchain log_login failed: {e}")
            # ────────────────────────────────────────────────────────────────

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
    if 'username' not in session:
        flash('Please log in to access hospital dashboard', 'warning')
        return redirect(url_for('login'))
    if session.get('role') == 'hospital' and session.get('username') != hospital_id:
        flash('Access denied for this hospital account', 'danger')
        return redirect(url_for('index'))

    ensure_hospital_dir(hospital_id)
    upload_info = get_last_upload_info(hospital_id)

    rm           = get_round_manager()
    round_status = rm.get_round_status()

    # Build submission history with real metrics from metadata.json
    hospital_submissions_dir = os.path.join(INCOMING_MODELS_DIR, hospital_id)
    submission_history = []
    if os.path.exists(hospital_submissions_dir):
        for folder in sorted(os.listdir(hospital_submissions_dir)):
            if not folder.startswith('round_'):
                continue
            try:
                rn  = int(folder.split('_')[1])
                mdp = os.path.join(hospital_submissions_dir, folder, 'metadata.json')
                if os.path.exists(mdp):
                    with open(mdp) as f:
                        md = json.load(f)
                    m = md.get('metrics', {})
                    submission_history.append({
                        'round':      rn,
                        'accuracy':   round(m.get('accuracy', 0) * 100, 2),
                        'loss':       round(m.get('loss', 0), 4),
                        'f1_score':   round(m.get('f1_score', 0), 4),
                        'timestamp':  md.get('received_at', '')[:10],
                        'dp_enabled': m.get('dp_info', {}).get('enabled', False)
                    })
            except Exception:
                pass
    submission_history.sort(key=lambda x: x['round'], reverse=True)

    # Load saved dataset path
    saved_path = load_dataset_paths().get(hospital_id, '')

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
        return redirect(url_for('hospital_dashboard', hospital_id=hospital_id))

    return render_template(
        'hospital.html',
        hospital_id=hospital_id,
        upload_info=upload_info,
        round_status=round_status,
        hospital_rounds=[s['round'] for s in submission_history],
        submission_history=submission_history,
        saved_dataset_path=saved_path
    )


@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if 'username' not in session or session.get('role') != 'admin':
        flash('Admin access required', 'warning')
        return redirect(url_for('login'))

    rm = get_round_manager()
    round_status = rm.get_round_status()

    # ── FIX: use hospital_1 format (underscore) everywhere ──────────────────
    hospitals = []
    for hid in ALL_HOSPITAL_IDS:
        has_submitted = hid in round_status['received_hospitals']
        last_submission = None

        hospital_submissions_dir = os.path.join(INCOMING_MODELS_DIR, hid)
        if os.path.exists(hospital_submissions_dir):
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
                    except Exception:
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

    model_status = load_metrics(MODELS_DIR, LOGS_DIR)

    return render_template(
        'admin.html',
        hospitals=hospitals,
        model_status=model_status,
        round_status=round_status
    )


@app.route('/model-status')
def model_status():
    metrics_data = load_federated_metrics(DATA_DIR)

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
        status = {
            'model_available': False,
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
    metrics = load_federated_metrics(DATA_DIR)
    if metrics.get("available"):
        metrics["last_updated_formatted"] = format_timestamp(metrics.get("last_updated"))
        metrics["status_text"] = get_model_status_text(metrics)
    return render_template('federated_metrics.html', metrics=metrics)


@app.route('/blockchain-ledger')
def blockchain_ledger():
    """
    Blockchain audit trail page.
    Shows all FL events logged on-chain.
    """
    return render_template('blockchain_ledger.html', events=[])


# ============================================================================
# FL API ENDPOINTS
# ============================================================================

@app.route('/api/submit_update', methods=['POST'])
def submit_model_update():
    """
    Hospital submits local model weights after training.

    Required:
        Form fields: hospital_id, round, metrics (JSON string with accuracy, loss, num_samples)
        File:        weights (.pt or .pth, max 200MB)
        Header:      X-API-KEY

    Returns:
        200: success + aggregation_status
        400: validation error
        401: auth error
        409: duplicate submission
        413: file too large
        429: rate limited
    """
    hospital_id = request.form.get('hospital_id', '').strip()

    # ── RATE LIMIT ───────────────────────────────────────────────────────────
    if hospital_id and is_rate_limited(hospital_id):
        return jsonify({
            'success': False,
            'error': 'Rate limit exceeded. Maximum 10 submissions per minute.'
        }), 429

    # ── AUTHENTICATION ───────────────────────────────────────────────────────
    api_key = request.headers.get('X-API-KEY', '')
    if not hospital_id:
        return jsonify({'success': False, 'error': 'Missing hospital_id in form data'}), 400
    if not api_key:
        return jsonify({'success': False, 'error': 'Missing X-API-KEY header'}), 401
    if not verify_api_key(hospital_id, api_key):
        app.logger.warning(f"AUTH FAILED: Invalid API key for hospital {hospital_id}")
        return jsonify({'success': False, 'error': 'Invalid API key for hospital'}), 401

    # ── ROUND VALIDATION ─────────────────────────────────────────────────────
    try:
        round_num = int(request.form.get('round', -1))
        if round_num < 1:
            raise ValueError("Round must be >= 1")
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'Invalid round number. Must be integer >= 1'}), 400

    previous_rounds = get_hospital_submissions(hospital_id)
    if previous_rounds and round_num <= max(previous_rounds):
        return jsonify({
            'success': False,
            'error': f'Round {round_num} already submitted. Expected > {max(previous_rounds)}'
        }), 409

    # ── FILE VALIDATION ──────────────────────────────────────────────────────
    if 'weights' not in request.files:
        return jsonify({'success': False, 'error': 'Missing weights file in form data'}), 400

    weights_file = request.files['weights']
    if weights_file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400

    filename = secure_filename(weights_file.filename)
    file_ext = os.path.splitext(filename)[1].lower()
    if file_ext not in ALLOWED_WEIGHT_EXTENSIONS:
        return jsonify({
            'success': False,
            'error': f'Invalid file type. Allowed: {", ".join(ALLOWED_WEIGHT_EXTENSIONS)}'
        }), 400

    weights_file.seek(0, os.SEEK_END)
    file_size = weights_file.tell()
    weights_file.seek(0)

    if file_size > MAX_WEIGHT_FILE_SIZE:
        return jsonify({
            'success': False,
            'error': f'File too large. Maximum size: {MAX_WEIGHT_FILE_SIZE / (1024*1024):.0f} MB'
        }), 413

    # ── METRICS VALIDATION ───────────────────────────────────────────────────
    metrics_raw = request.form.get('metrics', '{}')
    try:
        metrics = json.loads(metrics_raw)
    except json.JSONDecodeError:
        return jsonify({'success': False, 'error': 'Invalid metrics JSON'}), 400

    # num_samples is now REQUIRED (needed for correct FedAvg weighting)
    required_metric_keys = {'accuracy', 'loss', 'num_samples'}
    missing_keys = required_metric_keys - set(metrics.keys())
    if missing_keys:
        return jsonify({
            'success': False,
            'error': f'Metrics must contain: {", ".join(required_metric_keys)}. Missing: {", ".join(missing_keys)}'
        }), 400

    try:
        accuracy = float(metrics['accuracy'])
        loss = float(metrics['loss'])
        num_samples = int(metrics['num_samples'])
        if not (0 <= accuracy <= 1):
            raise ValueError("accuracy must be between 0 and 1")
        if loss < 0:
            raise ValueError("loss must be non-negative")
        if num_samples < 1:
            raise ValueError("num_samples must be >= 1")
    except (ValueError, TypeError) as e:
        return jsonify({'success': False, 'error': f'Invalid metric values: {str(e)}'}), 400

    # ── SAVE WEIGHTS ─────────────────────────────────────────────────────────
    hospital_round_dir = os.path.join(INCOMING_MODELS_DIR, hospital_id, f'round_{round_num}')
    os.makedirs(hospital_round_dir, exist_ok=True)

    weights_path = os.path.join(hospital_round_dir, 'weights.pt')
    try:
        weights_file.save(weights_path)
    except Exception as e:
        app.logger.error(f"Failed to save weights for {hospital_id}: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to save weights file'}), 500

    # ── SHA-256 INTEGRITY ────────────────────────────────────────────────────
    try:
        sha256_hash = hashlib.sha256()
        with open(weights_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                sha256_hash.update(chunk)
        file_hash = sha256_hash.hexdigest()
    except Exception as e:
        return jsonify({'success': False, 'error': 'Failed to verify file integrity'}), 500

    with open(os.path.join(hospital_round_dir, 'weights.sha256'), 'w') as f:
        f.write(file_hash)

    # ── SAVE METADATA ────────────────────────────────────────────────────────
    uploader_ip = request.remote_addr
    received_at = datetime.datetime.utcnow().isoformat() + 'Z'

    metadata = {
        'hospital_id': hospital_id,
        'round': round_num,
        'filename': 'weights.pt',
        'sha256': file_hash,
        'file_size_bytes': file_size,
        'metrics': {
            'accuracy': accuracy,
            'loss': loss,
            'num_samples': num_samples,
            'precision': float(metrics.get('precision', accuracy)),
            'recall': float(metrics.get('recall', accuracy)),
            'f1_score': float(metrics.get('f1_score', accuracy)),
            'auc_roc': float(metrics.get('auc_roc', accuracy)),
            'timestamp': received_at,
            'dp_info': metrics.get('dp_info', {'enabled': False})
        },
        'received_at': received_at,
        'uploader_ip': uploader_ip
    }

    metadata_path = os.path.join(hospital_round_dir, 'metadata.json')
    try:
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
    except Exception as e:
        app.logger.error(f"Failed to save metadata: {str(e)}")

    app.logger.info(
        f"MODEL UPDATE RECEIVED | hospital={hospital_id} | round={round_num} | "
        f"accuracy={accuracy:.4f} | loss={loss:.4f} | samples={num_samples} | "
        f"hash={file_hash[:16]}... | size={file_size/(1024*1024):.2f}MB | ip={uploader_ip}"
    )
    update_comm_log(round_num, hospital_id, file_size)

    # ── BLOCKCHAIN HOOK ──────────────────────────────────────────────────────
    try:
        log_submission_event(
            hospital_id=hospital_id,
            round_num=round_num,
            weights_hash=file_hash,
            accuracy=accuracy,
            num_samples=num_samples
        )
    except Exception as e:
        app.logger.warning(f"Blockchain log_submission failed: {e}")
    # ────────────────────────────────────────────────────────────────────────

    # ── REGISTER WITH ROUND MANAGER ──────────────────────────────────────────
    rm = get_round_manager()
    submission_status = rm.register_submission(
        hospital_id=hospital_id,
        weights_path=weights_path,
        num_samples=num_samples
    )

    # ── TRIGGER FEDAVG IF ALL HOSPITALS SUBMITTED ────────────────────────────
    if submission_status['ready_for_aggregation']:
        app.logger.info(
            f"[FEDAVG] All hospitals submitted for round {round_num}. Triggering aggregation..."
        )
        try:
            aggregator = FedAvgAggregator()
            current_round = rm.get_current_round()
            rm.mark_aggregation_start()

            submissions = rm.get_submissions_for_round(current_round)
            success, agg_msg, agg_metadata = aggregator.aggregate(
                submissions=submissions,
                global_round=current_round,
                output_dir=os.path.join(MODELS_DIR, 'global')
            )

            if success:
                global_model_path = agg_metadata['global_model_path']
                app.logger.info(
                    f"[FEDAVG] Aggregation complete | path={global_model_path} | "
                    f"hospitals={agg_metadata['total_hospitals']} | "
                    f"samples={agg_metadata['total_samples']}"
                )

                # ── UPDATE REAL METRICS ──────────────────────────────────────
                round_metadata = collect_round_metadata(current_round)
                update_federated_metrics_after_aggregation(current_round, round_metadata)

                rm.mark_aggregation_complete(global_model_path)

                # ── BLOCKCHAIN HOOK ──────────────────────────────────────────
                try:
                    global_hash = compute_file_hash(global_model_path)
                    log_aggregation_event(
                        round_num=current_round,
                        global_model_hash=global_hash,
                        hospitals=list(submissions.keys()),
                        total_samples=agg_metadata['total_samples']
                    )
                except Exception as e:
                    app.logger.warning(f"Blockchain log_aggregation failed: {e}")
                # ────────────────────────────────────────────────────────────

            else:
                app.logger.error(f"[FEDAVG] Aggregation failed: {agg_msg}")

        except Exception as e:
            app.logger.exception(f"[FEDAVG] Unexpected error during aggregation: {str(e)}")

    return jsonify({
        'success': True,
        'message': f'Model update for round {round_num} received successfully',
        'hospital_id': hospital_id,
        'round': round_num,
        'weights_hash': file_hash,
        'aggregation_status': submission_status.get('status', 'registered'),
        'submissions_received': len(submission_status.get('received_hospitals', [])),
        'submissions_expected': submission_status.get('expected_hospitals', 5)
    }), 200


@app.route('/api/global-model/latest', methods=['GET'])
def get_global_model():
    """
    Hospitals download the latest aggregated global model.
    No auth required — model weights contain no patient data.
    """
    try:
        global_models_dir = os.path.join(MODELS_DIR, 'global')

        if not os.path.exists(global_models_dir):
            return jsonify({'error': 'No global model available yet'}), 404

        available_rounds = []
        for filename in os.listdir(global_models_dir):
            if filename.startswith('global_model_round') and filename.endswith('.pt'):
                try:
                    round_num = int(filename.replace('global_model_round', '').replace('.pt', ''))
                    available_rounds.append(round_num)
                except ValueError:
                    pass

        if not available_rounds:
            return jsonify({'error': 'No global model available yet'}), 404

        latest_round = max(available_rounds)
        global_model_path = os.path.join(global_models_dir, f'global_model_round{latest_round}.pt')

        if not os.path.exists(global_model_path):
            return jsonify({'error': 'Model file not found'}), 404

        # Compute hash for integrity header
        sha256_hash = hashlib.sha256()
        with open(global_model_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                sha256_hash.update(chunk)
        model_hash = sha256_hash.hexdigest()

        file_size = os.path.getsize(global_model_path)
        app.logger.info(
            f"[DOWNLOAD] Global model | round={latest_round} | ip={request.remote_addr}"
        )

        response = send_file(
            global_model_path,
            mimetype='application/octet-stream',
            as_attachment=True,
            download_name=f'global_model_round{latest_round}.pt'
        )
        response.headers['X-GLOBAL-ROUND'] = str(latest_round)
        response.headers['X-MODEL-HASH'] = model_hash
        response.headers['X-FILE-SIZE'] = str(file_size)
        return response

    except Exception as e:
        app.logger.exception(f"Error serving global model: {str(e)}")
        return jsonify({'error': 'Internal server error', 'message': str(e)}), 500


@app.route('/api/round-status', methods=['GET'])
def get_round_status():
    """Current round status — used by website auto-refresh and hospital notebooks."""
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
        return jsonify({'error': 'Internal server error', 'message': str(e)}), 500


@app.route('/api/blockchain-events', methods=['GET'])
def api_blockchain_events():
    """
    Returns all blockchain events as JSON.
    Called by /blockchain-ledger page every 5s for live updates.
    """
    # ── BLOCKCHAIN HOOK (Phase 2) ────────────────────────────────────────────
    from blockchain_bridge import get_all_events
    events = get_all_events()
    return jsonify({'success': True, 'events': events})
    # ────────────────────────────────────────────────────────────────────────
    return jsonify({'success': True, 'events': []})


@app.route('/api/append-metrics-round', methods=['POST'])
def api_append_metrics_round():
    """Admin-only: manually append a training round to metrics (for testing)."""
    if 'username' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Admin access required'}), 401

    data = request.get_json()
    required_fields = ['round', 'accuracy', 'precision', 'recall', 'f1_score', 'loss', 'auc_roc']
    if not all(field in data for field in required_fields):
        return jsonify({'success': False, 'error': 'Missing required fields'}), 400

    try:
        metrics_path = os.path.join(DATA_DIR, 'federated_metrics.json')
        if not os.path.exists(metrics_path):
            return jsonify({'success': False, 'error': 'Metrics file not found'}), 404

        with open(metrics_path, 'r') as f:
            metrics = json.load(f)

        timestamp = data.get('timestamp', datetime.datetime.now().isoformat())
        metrics['last_updated'] = timestamp
        metrics['training_rounds'] = data['round']
        metrics['accuracy_per_round'].append(data['accuracy'])
        metrics['precision_per_round'].append(data['precision'])
        metrics['recall_per_round'].append(data['recall'])
        metrics['f1_score_per_round'].append(data['f1_score'])
        metrics['loss_per_round'].append(data['loss'])
        metrics['auc_roc_per_round'].append(data['auc_roc'])
        metrics['final_accuracy'] = data['accuracy'] * 100
        metrics['final_precision'] = data['precision'] * 100
        metrics['final_recall'] = data['recall'] * 100
        metrics['final_f1_score'] = data['f1_score']
        metrics['final_loss'] = data['loss']
        metrics['final_auc_roc'] = data['auc_roc'] * 100
        metrics['institutions_participated'] = data.get('institutions_participated', 5)
        metrics['training_history'].append({
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
        })

        with open(metrics_path, 'w') as f:
            json.dump(metrics, f, indent=2)

        return jsonify({'success': True, 'message': f"Round {data['round']} appended"}), 200

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/reset-demo', methods=['POST'])
def api_reset_demo():
    """
    Admin-only: Reset all FL state for a clean demo run.
    Clears round_state.json, incoming models, global models, and metrics.
    """
    if 'username' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Admin access required'}), 401

    import shutil

    try:
        # Reset round state
        rm = get_round_manager()
        rm.reset_round()

        # Wipe round counter back to 1
        state_file = os.path.join(DATA_DIR, 'round_state.json')
        with open(state_file, 'r') as f:
            state = json.load(f)
        state['current_round'] = 1
        state['received_updates'] = []
        state['submissions'] = {}
        state['aggregation_status'] = 'pending'
        state['last_aggregation'] = None
        with open(state_file, 'w') as f:
            json.dump(state, f, indent=2)

        # Clear incoming models
        if os.path.exists(INCOMING_MODELS_DIR):
            shutil.rmtree(INCOMING_MODELS_DIR)
        os.makedirs(INCOMING_MODELS_DIR, exist_ok=True)

        # Clear global models
        global_dir = os.path.join(MODELS_DIR, 'global')
        if os.path.exists(global_dir):
            shutil.rmtree(global_dir)
        os.makedirs(global_dir, exist_ok=True)

        # Reset metrics to empty
        metrics_path = os.path.join(DATA_DIR, 'federated_metrics.json')
        empty_metrics = {
            "model_id": "medledger_global_v1",
            "last_updated": datetime.datetime.utcnow().isoformat(),
            "institutions_participated": 5,
            "training_rounds": 0,
            "accuracy_per_round": [],
            "precision_per_round": [],
            "recall_per_round": [],
            "f1_score_per_round": [],
            "loss_per_round": [],
            "auc_roc_per_round": [],
            "final_accuracy": 0,
            "final_precision": 0,
            "final_recall": 0,
            "final_f1_score": 0,
            "final_loss": 0,
            "final_auc_roc": 0,
            "model_status": "not_trained",
            "training_history": []
        }
        with open(metrics_path, 'w') as f:
            json.dump(empty_metrics, f, indent=2)

        app.logger.info("[RESET] Demo state reset by admin")
        return jsonify({'success': True, 'message': 'Demo reset complete. Ready for round 1.'}), 200

    except Exception as e:
        app.logger.exception(f"Demo reset failed: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# AGENT HEARTBEAT — tracks online/offline status per hospital
# ============================================================================

AGENT_HEARTBEAT_FILE = os.path.join(DATA_DIR, 'agent_heartbeats.json')
AGENT_TIMEOUT_SECS   = 15  # agent considered offline after 15s no ping


def load_heartbeats():
    if not os.path.exists(AGENT_HEARTBEAT_FILE):
        return {}
    try:
        with open(AGENT_HEARTBEAT_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_heartbeats(hb):
    try:
        with open(AGENT_HEARTBEAT_FILE, 'w') as f:
            json.dump(hb, f, indent=2)
    except Exception:
        pass


@app.route('/api/agent-heartbeat', methods=['POST'])
def agent_heartbeat():
    """Agent pings this every 5s to show it's online."""
    data        = request.get_json() or {}
    hospital_id = data.get('hospital_id', '').strip()
    if not hospital_id:
        return jsonify({'success': False, 'error': 'Missing hospital_id'}), 400

    hb = load_heartbeats()
    hb[hospital_id] = {
        'last_seen':  datetime.datetime.utcnow().isoformat() + 'Z',
        'timestamp':  datetime.datetime.utcnow().timestamp()
    }
    save_heartbeats(hb)
    return jsonify({'success': True}), 200


@app.route('/api/agent-status', methods=['GET'])
def agent_status():
    """Returns online/offline status for all hospitals."""
    hb  = load_heartbeats()
    now = datetime.datetime.utcnow().timestamp()
    result = {}
    for hid in ALL_HOSPITAL_IDS:
        entry    = hb.get(hid)
        if entry:
            age      = now - entry.get('timestamp', 0)
            online   = age < AGENT_TIMEOUT_SECS
            result[hid] = {
                'online':    online,
                'last_seen': entry.get('last_seen', 'never'),
                'age_secs':  round(age, 1)
            }
        else:
            result[hid] = {'online': False, 'last_seen': 'never', 'age_secs': None}
    return jsonify({'success': True, 'agents': result}), 200


# ============================================================================
# DATASET PATH MEMORY — saves hospital's last used dataset path
# ============================================================================

DATASET_PATHS_FILE = os.path.join(DATA_DIR, 'dataset_paths.json')


def load_dataset_paths():
    if not os.path.exists(DATASET_PATHS_FILE):
        return {}
    try:
        with open(DATASET_PATHS_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


@app.route('/api/save-dataset-path', methods=['POST'])
def save_dataset_path():
    """Saves hospital's dataset path so it's remembered next visit."""
    if 'username' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401
    data         = request.get_json() or {}
    hospital_id  = data.get('hospital_id', '').strip()
    dataset_path = data.get('dataset_path', '').strip()
    if not hospital_id or not dataset_path:
        return jsonify({'success': False, 'error': 'Missing fields'}), 400

    paths = load_dataset_paths()
    paths[hospital_id] = dataset_path
    try:
        with open(DATASET_PATHS_FILE, 'w') as f:
            json.dump(paths, f, indent=2)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    return jsonify({'success': True}), 200


@app.route('/api/get-dataset-path/<hospital_id>', methods=['GET'])
def get_dataset_path(hospital_id):
    """Returns saved dataset path for a hospital."""
    paths = load_dataset_paths()
    return jsonify({'success': True, 'path': paths.get(hospital_id, '')}), 200


# ============================================================================
# COMMUNICATION COST TRACKING
# ============================================================================

COMM_LOG_FILE           = os.path.join(DATA_DIR, 'communication_log.json')
CENTRALIZED_RESULTS_FILE = os.path.join(DATA_DIR, 'centralized_results.json')


def load_comm_log():
    if not os.path.exists(COMM_LOG_FILE):
        return {'rounds': [], 'total_mb_transmitted': 0}
    try:
        with open(COMM_LOG_FILE) as f:
            return json.load(f)
    except Exception:
        return {'rounds': [], 'total_mb_transmitted': 0}


def update_comm_log(round_num: int, hospital_id: str, file_size_bytes: int):
    log     = load_comm_log()
    size_mb = round(file_size_bytes / (1024 * 1024), 3)

    round_entry = next((r for r in log['rounds'] if r['round'] == round_num), None)
    if not round_entry:
        round_entry = {
            'round':       round_num,
            'submissions': [],
            'total_mb':    0,
            'timestamp':   datetime.datetime.utcnow().isoformat() + 'Z'
        }
        log['rounds'].append(round_entry)

    round_entry['submissions'].append({
        'hospital_id': hospital_id,
        'size_mb':     size_mb,
        'timestamp':   datetime.datetime.utcnow().isoformat() + 'Z'
    })
    round_entry['total_mb'] = round(
        sum(s['size_mb'] for s in round_entry['submissions']), 3
    )
    log['total_mb_transmitted'] = round(
        sum(r['total_mb'] for r in log['rounds']), 3
    )
    try:
        with open(COMM_LOG_FILE, 'w') as f:
            json.dump(log, f, indent=2)
    except Exception as e:
        app.logger.error(f"Failed to update comm log: {e}")


@app.route('/api/communication-stats', methods=['GET'])
def get_communication_stats():
    log  = load_comm_log()
    RAW  = 250.0  # estimated raw data per hospital MB
    stats = {
        'rounds':                  [],
        'total_mb_transmitted':    log.get('total_mb_transmitted', 0),
        'total_raw_data_estimate': 0,
        'total_savings_pct':       0
    }
    for r in log.get('rounds', []):
        n          = len(r.get('submissions', []))
        raw        = round(n * RAW, 1)
        actual     = r['total_mb']
        savings    = round((1 - actual / (raw + 1e-8)) * 100, 1) if raw > 0 else 0
        stats['rounds'].append({
            'round':           r['round'],
            'total_mb':        actual,
            'num_hospitals':   n,
            'raw_estimate_mb': raw,
            'savings_pct':     savings,
            'submissions':     r.get('submissions', [])
        })
    if stats['rounds']:
        total_raw  = sum(r['raw_estimate_mb'] for r in stats['rounds'])
        total_act  = stats['total_mb_transmitted']
        stats['total_raw_data_estimate'] = round(total_raw, 1)
        stats['total_savings_pct']       = round(
            (1 - total_act / (total_raw + 1e-8)) * 100, 1
        )
    return jsonify({'success': True, 'stats': stats}), 200


@app.route('/api/per-hospital-metrics', methods=['GET'])
def get_per_hospital_metrics():
    result = {}
    for hid in ALL_HOSPITAL_IDS:
        hospital_dir = os.path.join(INCOMING_MODELS_DIR, hid)
        if not os.path.exists(hospital_dir):
            continue
        rounds_data = []
        for folder in sorted(os.listdir(hospital_dir)):
            if not folder.startswith('round_'):
                continue
            try:
                rn   = int(folder.split('_')[1])
                path = os.path.join(hospital_dir, folder, 'metadata.json')
                if os.path.exists(path):
                    with open(path) as f:
                        md = json.load(f)
                    m       = md.get('metrics', {})
                    dp_info = m.get('dp_info', {'enabled': False})
                    rounds_data.append({
                        'round':      rn,
                        'accuracy':   m.get('accuracy', 0),
                        'loss':       m.get('loss', 0),
                        'f1_score':   m.get('f1_score', 0),
                        'dp_enabled': dp_info.get('enabled', False),
                        'epsilon':    dp_info.get('epsilon', None)
                    })
            except Exception:
                pass
        if rounds_data:
            result[hid] = sorted(rounds_data, key=lambda x: x['round'])
    return jsonify({'success': True, 'hospitals': result}), 200


@app.route('/api/centralized-results', methods=['GET'])
def get_centralized_results():
    if not os.path.exists(CENTRALIZED_RESULTS_FILE):
        return jsonify({'success': True, 'available': False,
                        'message': 'Run: python scripts/centralized_train.py'}), 200
    try:
        with open(CENTRALIZED_RESULTS_FILE) as f:
            results = json.load(f)
        return jsonify({'success': True, 'available': True, 'results': results}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/research-summary', methods=['GET'])
def get_research_summary():
    fl_metrics   = load_federated_metrics(DATA_DIR)
    centralized  = None
    if os.path.exists(CENTRALIZED_RESULTS_FILE):
        try:
            with open(CENTRALIZED_RESULTS_FILE) as f:
                centralized = json.load(f)
        except Exception:
            pass

    comm_log     = load_comm_log()
    per_hospital = {}
    for hid in ALL_HOSPITAL_IDS:
        hospital_dir = os.path.join(INCOMING_MODELS_DIR, hid)
        if not os.path.exists(hospital_dir):
            continue
        rounds_data = []
        for folder in sorted(os.listdir(hospital_dir)):
            if not folder.startswith('round_'):
                continue
            try:
                rn   = int(folder.split('_')[1])
                path = os.path.join(hospital_dir, folder, 'metadata.json')
                if os.path.exists(path):
                    with open(path) as f:
                        md = json.load(f)
                    m       = md.get('metrics', {})
                    dp_info = m.get('dp_info', {'enabled': False})
                    rounds_data.append({
                        'round':      rn,
                        'accuracy':   m.get('accuracy', 0),
                        'loss':       m.get('loss', 0),
                        'dp_enabled': dp_info.get('enabled', False),
                        'epsilon':    dp_info.get('epsilon', None)
                    })
            except Exception:
                pass
        if rounds_data:
            per_hospital[hid] = sorted(rounds_data, key=lambda x: x['round'])

    gap = None
    if centralized and fl_metrics.get('available'):
        fl_acc   = fl_metrics.get('final_accuracy', 0)
        cent_acc = centralized.get('accuracy', 0) * 100
        gap      = round(cent_acc - fl_acc, 2)

    return jsonify({
        'success':      True,
        'fl_metrics':   fl_metrics,
        'centralized':  centralized,
        'comm_log':     comm_log,
        'per_hospital': per_hospital,
        'accuracy_gap': gap
    }), 200

# ============================================================================
# TRAINING JOB MANAGEMENT ROUTES
# Add these routes to app.py above the if __name__ == '__main__': line
# ============================================================================

TRAINING_JOBS_FILE = os.path.join(DATA_DIR, 'training_jobs.json')

DISEASE_DOMAINS = {
    'pneumonia':           {'name': 'Pneumonia Detection',       'classes': ['NORMAL', 'PNEUMONIA']},
    'bone_fracture':       {'name': 'Bone Fracture Detection',   'classes': ['NORMAL', 'FRACTURED']},
    'diabetic_retinopathy':{'name': 'Diabetic Retinopathy',      'classes': ['No_DR', 'DR']},
    'brain_tumor':         {'name': 'Brain Tumor Detection',     'classes': ['no_tumor', 'tumor']},
    'skin_lesion':         {'name': 'Skin Lesion Classification','classes': ['benign', 'malignant']},
}


def load_training_jobs():
    if not os.path.exists(TRAINING_JOBS_FILE):
        return {}
    try:
        with open(TRAINING_JOBS_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return {}


def save_training_jobs(jobs):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(TRAINING_JOBS_FILE, 'w') as f:
        json.dump(jobs, f, indent=2)


@app.route('/api/start-training-job', methods=['POST'])
def start_training_job():
    """
    Hospital clicks Start Training on the website.
    Creates a job entry that the hospital_agent.py picks up.

    POST JSON:
    {
        "hospital_id":    "hospital_1",
        "disease_domain": "pneumonia",
        "dataset_path":   "C:\\data\\hospitals\\hospital_1",
        "epochs":         5,
        "round":          1
    }
    """
    if 'username' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401

    data = request.get_json()
    hospital_id    = data.get('hospital_id', '').strip()
    disease_domain = data.get('disease_domain', '').strip()
    dataset_path   = data.get('dataset_path', '').strip()
    epochs         = int(data.get('epochs', 5))
    round_num      = int(data.get('round', 1))

    # Validate
    if not hospital_id:
        return jsonify({'success': False, 'error': 'Missing hospital_id'}), 400
    if disease_domain not in DISEASE_DOMAINS:
        return jsonify({'success': False, 'error': f'Unknown disease domain: {disease_domain}'}), 400
    if not dataset_path:
        return jsonify({'success': False, 'error': 'Missing dataset_path'}), 400

    # Only allow hospital to create job for themselves
    if session.get('role') == 'hospital' and session.get('username') != hospital_id:
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    jobs = load_training_jobs()

    # Check if job already running
    existing = jobs.get(hospital_id, {})
    if existing.get('status') in ('pending', 'training'):
        return jsonify({
            'success': False,
            'error': 'Training already in progress for this hospital'
        }), 409

    # Create job
    job = {
        'hospital_id':    hospital_id,
        'disease_domain': disease_domain,
        'disease_name':   DISEASE_DOMAINS[disease_domain]['name'],
        'dataset_path':   dataset_path,
        'epochs':         epochs,
        'round':          round_num,
        'status':         'pending',       # pending → training → done / failed
        'current_epoch':  0,
        'total_epochs':   epochs,
        'progress_pct':   0,
        'latest_accuracy': None,
        'latest_loss':     None,
        'logs':           [],
        'created_at':     datetime.datetime.utcnow().isoformat() + 'Z',
        'started_at':     None,
        'finished_at':    None,
        'error':          None,
    }

    jobs[hospital_id] = job
    save_training_jobs(jobs)

    app.logger.info(f"[JOB] Created training job | hospital={hospital_id} | domain={disease_domain} | round={round_num}")

    return jsonify({
        'success': True,
        'message': f'Training job created for {hospital_id}',
        'job': job
    }), 200


@app.route('/api/my-job/<hospital_id>', methods=['GET'])
def get_my_job(hospital_id):
    """
    hospital_agent.py polls this every 2 seconds.
    Returns the pending job for this hospital if one exists.
    """
    jobs = load_training_jobs()
    job  = jobs.get(hospital_id)

    if not job:
        return jsonify({'success': True, 'job': None}), 200

    # Only return job if it needs action from the agent
    if job['status'] in ('pending', 'training'):
        return jsonify({'success': True, 'job': job}), 200

    return jsonify({'success': True, 'job': job}), 200


@app.route('/api/job-progress', methods=['POST'])
def update_job_progress():
    """
    hospital_agent.py posts progress updates here after each epoch.

    POST JSON:
    {
        "hospital_id":  "hospital_1",
        "status":       "training",
        "current_epoch": 2,
        "total_epochs":  5,
        "accuracy":     0.8721,
        "loss":         0.3412,
        "log":          "Epoch 2/5 | loss=0.3412 | acc=87.21%"
    }
    """
    data        = request.get_json()
    hospital_id = data.get('hospital_id', '').strip()

    if not hospital_id:
        return jsonify({'success': False, 'error': 'Missing hospital_id'}), 400

    jobs = load_training_jobs()
    job  = jobs.get(hospital_id)

    if not job:
        return jsonify({'success': False, 'error': 'No job found for this hospital'}), 404

    # Update job fields
    job['status']         = data.get('status', job['status'])
    job['current_epoch']  = data.get('current_epoch', job['current_epoch'])
    job['total_epochs']   = data.get('total_epochs',  job['total_epochs'])
    job['latest_accuracy']= data.get('accuracy',      job['latest_accuracy'])
    job['latest_loss']    = data.get('loss',           job['latest_loss'])

    # Progress percentage
    if job['total_epochs'] > 0:
        job['progress_pct'] = int((job['current_epoch'] / job['total_epochs']) * 100)

    # Append log line
    log_line = data.get('log')
    if log_line:
        job['logs'].append(log_line)
        if len(job['logs']) > 50:   # keep last 50 lines
            job['logs'] = job['logs'][-50:]

    # Set timestamps
    if job['status'] == 'training' and not job.get('started_at'):
        job['started_at'] = datetime.datetime.utcnow().isoformat() + 'Z'

    if job['status'] in ('done', 'failed'):
        job['finished_at'] = datetime.datetime.utcnow().isoformat() + 'Z'
        if job['status'] == 'failed':
            job['error'] = data.get('error', 'Unknown error')

    if job['status'] == 'done':
        job['progress_pct'] = 100

    jobs[hospital_id] = job
    save_training_jobs(jobs)

    return jsonify({'success': True}), 200


@app.route('/api/job-status/<hospital_id>', methods=['GET'])
def get_job_status(hospital_id):
    """
    Browser polls this every 2 seconds to update the progress bar.
    """
    jobs = load_training_jobs()
    job  = jobs.get(hospital_id)

    if not job:
        return jsonify({'success': True, 'job': None}), 200

    return jsonify({'success': True, 'job': job}), 200


@app.route('/api/cancel-job/<hospital_id>', methods=['POST'])
def cancel_job(hospital_id):
    """Cancel a pending or failed job so hospital can start fresh."""
    if 'username' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401
    if session.get('role') == 'hospital' and session.get('username') != hospital_id:
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    jobs = load_training_jobs()
    if hospital_id in jobs:
        jobs[hospital_id]['status'] = 'cancelled'
        save_training_jobs(jobs)

    return jsonify({'success': True}), 200


@app.route('/api/disease-domains', methods=['GET'])
def get_disease_domains():
    """Returns available disease domains for the dropdown."""
    return jsonify({'success': True, 'domains': DISEASE_DOMAINS}), 200

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)