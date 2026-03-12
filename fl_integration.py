"""
Federated Learning Integration Utilities
========================================

This module bridges the gap between the Federated Learning training
notebook and the Flask website.

DESIGN PHILOSOPHY:
  - Training runs independently in the notebook (Colab environment)
  - Website reads exported model artifacts as read-only files
  - No PyTorch imports or model execution in Flask
  - Clean separation of concerns for healthcare privacy & security

INTEGRATION POINTS:
  - models/global_model.pt : Trained PyTorch model state dict
  - logs/metrics.json      : Training metrics (rounds, accuracy, timestamp)
"""

import os
import json
from typing import Optional, Dict, Any


def load_metrics(models_dir: str, logs_dir: str) -> Dict[str, Any]:
    """
    Load Federated Learning metrics from JSON file.
    
    This function safely reads the metrics exported from the training notebook.
    If files are missing, it returns a "not trained yet" status.
    
    Args:
        models_dir: Path to models directory (contains global_model.pt)
        logs_dir:   Path to logs directory (contains metrics.json)
    
    Returns:
        Dictionary with keys:
        - model_available (bool): True if global_model.pt exists
        - rounds_completed (int): Number of FL rounds completed
        - accuracy (float): Final test accuracy percentage
        - loss (float|None): Final loss value (if available)
        - last_updated (str): ISO timestamp of last training
    """
    
    # Federated Learning integration point: Check model file existence
    model_path = os.path.join(models_dir, "global_model.pt")
    model_exists = os.path.isfile(model_path)
    
    # Default response if model not trained
    default_status = {
        "model_available": False,
        "rounds_completed": "N/A",
        "accuracy": "Not trained yet",
        "loss": None,
        "last_updated": "N/A"
    }
    
    # If model doesn't exist, return default status
    if not model_exists:
        return default_status
    
    # Try to load metrics from JSON
    metrics_path = os.path.join(logs_dir, "metrics.json")
    
    if not os.path.isfile(metrics_path):
        # Model exists but metrics file missing (shouldn't happen)
        return {
            "model_available": True,
            "rounds_completed": "Unknown",
            "accuracy": "Unknown",
            "loss": None,
            "last_updated": "Unknown"
        }
    
    try:
        with open(metrics_path, 'r') as f:
            metrics = json.load(f)
        
        # Federated Learning integration point: Parse metrics
        # These values come directly from the training notebook
        return {
            "model_available": True,
            "rounds_completed": metrics.get("rounds_completed", "Unknown"),
            "accuracy": f"{metrics.get('accuracy', 'N/A')}%",
            "loss": metrics.get("loss"),
            "last_updated": metrics.get("last_updated", "Unknown")
        }
    
    except (json.JSONDecodeError, IOError) as e:
        # Metrics file corrupted or unreadable
        return {
            "model_available": True,
            "rounds_completed": "Error",
            "accuracy": "Error reading metrics",
            "loss": None,
            "last_updated": "Error"
        }


def get_model_info(models_dir: str) -> Dict[str, Any]:
    """
    Get basic information about the trained model file.
    
    Args:
        models_dir: Path to models directory
    
    Returns:
        Dictionary with model info or None if model doesn't exist
    """
    
    model_path = os.path.join(models_dir, "global_model.pt")
    
    if not os.path.isfile(model_path):
        return None
    
    try:
        file_size_mb = os.path.getsize(model_path) / (1024 * 1024)
        file_mtime = os.path.getmtime(model_path)
        
        import datetime
        last_modified = datetime.datetime.fromtimestamp(file_mtime)
        
        return {
            "exists": True,
            "size_mb": round(file_size_mb, 2),
            "last_modified": last_modified.strftime("%Y-%m-%d %H:%M:%S")
        }
    except Exception:
        return {"exists": True, "size_mb": "Unknown", "last_modified": "Unknown"}
