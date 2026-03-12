"""
Metrics Loader for Federated Learning Status
==============================================

Reads exported federated learning artifacts from JSON.
Provides read-only access to training metrics and model status.

Integration Point:
  - Consumes: /data/federated_metrics.json
  - Does not execute training
  - Does not modify files
  - Fails gracefully on missing artifacts
"""

import json
import os
from typing import Dict, Any, Optional


def load_federated_metrics(data_dir: str) -> Dict[str, Any]:
    """
    Load federated learning metrics from exported JSON artifact.
    
    Args:
        data_dir: Path to data directory (e.g., /data)
    
    Returns:
        Dictionary with metrics or empty dict with 'available': False if missing
    
    This function is read-only and never modifies files.
    """
    metrics_file = os.path.join(data_dir, "federated_metrics.json")
    
    # Default response when no metrics are available
    default_response = {
        "available": False,
        "model_id": None,
        "last_updated": None,
        "institutions_participated": 0,
        "training_rounds": 0,
        "accuracy_per_round": [],
        "loss_per_round": [],
        "final_accuracy": 0.0,
        "model_status": "unavailable"
    }
    
    # Check if file exists
    if not os.path.exists(metrics_file):
        return default_response
    
    try:
        with open(metrics_file, 'r') as f:
            metrics = json.load(f)
        
        # Validate required fields
        required_fields = [
            "model_id",
            "last_updated",
            "institutions_participated",
            "training_rounds",
            "final_accuracy",
            "model_status"
        ]
        
        if not all(field in metrics for field in required_fields):
            return default_response
        
        # Mark as available if all validation passes
        metrics["available"] = True
        
        return metrics
    
    except (json.JSONDecodeError, IOError, ValueError):
        # Any file read or JSON parse error
        return default_response


def get_model_status_text(metrics: Dict[str, Any]) -> str:
    """
    Get human-readable model status text.
    
    Args:
        metrics: Metrics dictionary from load_federated_metrics()
    
    Returns:
        Status string for display
    """
    if not metrics.get("available"):
        return "Model Not Loaded"
    
    status = metrics.get("model_status", "unavailable").lower()
    
    if status == "available":
        return "Trained Model Available"
    elif status == "training":
        return "Training in Progress"
    else:
        return "Model Status Unknown"


def format_timestamp(iso_string: Optional[str]) -> str:
    """
    Format ISO timestamp for display.
    
    Args:
        iso_string: ISO 8601 formatted timestamp
    
    Returns:
        Formatted string or 'Unknown' if invalid
    """
    if not iso_string:
        return "Unknown"
    
    try:
        # Parse ISO format and return readable format
        from datetime import datetime
        dt = datetime.fromisoformat(iso_string.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d %H:%M:%S UTC')
    except (ValueError, AttributeError):
        return "Invalid timestamp"
