"""
========================================================================
FEDERATED LEARNING ROUND MANAGER - Coordination Logic
========================================================================

RESPONSIBILITY:
    Track round state, manage submissions, trigger aggregation

NOT RESPONSIBLE FOR:
    Storing patient data
    Executing training
    Accessing hospital datasets

ARCHITECTURAL FLOW:
    Hospital 1 submits → store
    Hospital 2 submits → store
    Hospital 3 submits → store
    Hospital 4 submits → store
    Hospital 5 submits → ALL RECEIVED → trigger aggregation
                             ↓
                        Aggregate weights
                             ↓
                        Increment round
                             ↓
                        Hospitals download global model
"""

import json
import os
import logging
from datetime import datetime
from typing import Dict, List, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


class RoundManager:
    """
    Manage federated learning round state.
    
    Tracks:
        - Current round number
        - Expected number of hospitals
        - Which hospitals have submitted
        - Submission timestamps
    
    Persists to: data/round_state.json
    """
    
    def __init__(self, state_file: str = "data/round_state.json", expected_hospitals: int = 5):
        """
        Initialize round manager.
        
        Args:
            state_file: Path to persistent state JSON
            expected_hospitals: Number of hospitals in the network
        """
        self.state_file = state_file
        self.expected_hospitals = expected_hospitals
        self.logger = logging.getLogger(f"{__name__}.RoundManager")
        self._ensure_state_file()
    
    def _ensure_state_file(self):
        """Create initial state file if it doesn't exist."""
        if not os.path.exists(self.state_file):
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            initial_state = {
                "current_round": 1,
                "expected_hospitals": self.expected_hospitals,
                "received_updates": [],
                "submissions": {},
                "last_aggregation": None,
                "created_at": datetime.utcnow().isoformat() + 'Z'
            }
            self._write_state(initial_state)
            self.logger.info(f"✓ Created initial round state: {self.state_file}")
    
    def _read_state(self) -> dict:
        """Load current round state from disk."""
        try:
            with open(self.state_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Failed to read state: {str(e)}")
            return {}
    
    def _write_state(self, state: dict):
        """Persist round state to disk."""
        try:
            os.makedirs(os.path.dirname(self.state_file) or '.', exist_ok=True)
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            self.logger.error(f"Failed to write state: {str(e)}")
    
    def get_current_round(self) -> int:
        """Get the current federated learning round."""
        state = self._read_state()
        return state.get("current_round", 1)
    
    def register_submission(self, hospital_id: str, weights_path: str, num_samples: int) -> dict:
        """
        Register a hospital submission for the current round.
        
        Args:
            hospital_id: Hospital identifier (e.g., "hospital_1")
            weights_path: Path to local_model_roundN.pt file
            num_samples: Number of samples this hospital trained on
        
        Returns:
            {
                "status": "registered" | "round_complete",
                "current_round": int,
                "received_hospitals": [list],
                "expected_hospitals": int,
                "ready_for_aggregation": bool
            }
        """
        state = self._read_state()
        current_round = state.get("current_round", 1)
        
        # Register submission
        if hospital_id not in state["received_updates"]:
            state["received_updates"].append(hospital_id)
        
        # Store submission details
        state["submissions"][hospital_id] = {
            "weights_path": weights_path,
            "num_samples": num_samples,
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }
        
        self._write_state(state)
        
        self.logger.info(f"Registered {hospital_id} for round {current_round}")
        self.logger.info(f"  Submissions: {len(state['received_updates'])}/{state['expected_hospitals']}")
        
        # Check if all hospitals have submitted
        is_round_complete = len(state["received_updates"]) >= state["expected_hospitals"]
        
        return {
            "status": "round_complete" if is_round_complete else "registered",
            "current_round": current_round,
            "received_hospitals": state["received_updates"],
            "expected_hospitals": state["expected_hospitals"],
            "ready_for_aggregation": is_round_complete
        }
    
    def get_round_status(self) -> dict:
        """
        Get current round status.
        
        Returns:
            {
                "current_round": int,
                "expected_hospitals": int,
                "received_hospitals": [list],
                "missing_hospitals": [list],
                "ready_for_aggregation": bool,
                "aggregation_status": "pending" | "in_progress" | "complete"
            }
        """
        state = self._read_state()
        current_round = state.get("current_round", 1)
        received = state.get("received_updates", [])
        expected = state.get("expected_hospitals", 5)
        
        all_hospitals = [f"hospital_{i+1}" for i in range(expected)]
        missing = [h for h in all_hospitals if h not in received]
        
        return {
            "current_round": current_round,
            "expected_hospitals": expected,
            "received_hospitals": received,
            "missing_hospitals": missing,
            "ready_for_aggregation": len(received) >= expected,
            "aggregation_status": state.get("aggregation_status", "pending")
        }
    
    def get_submissions_for_round(self, round_num: int = None) -> Dict[str, Tuple[str, int]]:
        """
        Get all submissions for a specific round.
        
        Returns:
            {
                "hospital_1": ("path/to/weights.pt", 500),
                "hospital_2": ("path/to/weights.pt", 450),
                ...
            }
        """
        state = self._read_state()
        if round_num is None:
            round_num = state.get("current_round", 1)
        
        submissions = state.get("submissions", {})
        
        # Convert to format needed by FedAvg aggregator
        result = {}
        for hospital_id, submission_data in submissions.items():
            result[hospital_id] = (
                submission_data["weights_path"],
                submission_data["num_samples"]
            )
        
        return result
    
    def mark_aggregation_start(self):
        """Mark that aggregation has begun for the current round."""
        state = self._read_state()
        state["aggregation_status"] = "in_progress"
        state["aggregation_started_at"] = datetime.utcnow().isoformat() + 'Z'
        self._write_state(state)
        self.logger.info(f"Marked aggregation start for round {state['current_round']}")
    
    def mark_aggregation_complete(self, global_model_path: str):
        """
        Mark that aggregation is complete and increment round.
        
        Args:
            global_model_path: Path to the saved global_model_roundN.pt
        """
        state = self._read_state()
        current_round = state.get("current_round", 1)
        
        state["aggregation_status"] = "complete"
        state["last_aggregation"] = {
            "round": current_round,
            "timestamp": datetime.utcnow().isoformat() + 'Z',
            "global_model_path": global_model_path,
            "hospitals_aggregated": state.get("received_updates", [])
        }
        
        # Increment round and reset for next round
        state["current_round"] = current_round + 1
        state["received_updates"] = []
        state["submissions"] = {}
        state["aggregation_status"] = "pending"
        
        self._write_state(state)
        
        self.logger.info(f"✓ Marked aggregation complete for round {current_round}")
        self.logger.info(f"  Global model: {global_model_path}")
        self.logger.info(f"  Next round: {current_round + 1}")
    
    def reset_round(self):
        """Reset current round (admin use only)."""
        state = self._read_state()
        state["received_updates"] = []
        state["submissions"] = {}
        state["aggregation_status"] = "pending"
        self._write_state(state)
        self.logger.warning(f"Reset round {state.get('current_round', 1)}")


# Singleton instance for app.py
_round_manager = None


def get_round_manager(state_file: str = "data/round_state.json", expected_hospitals: int = 5) -> RoundManager:
    """
    Get or create the global round manager instance.
    
    Usage in app.py:
        from server.round_manager import get_round_manager
        
        rm = get_round_manager()
        status = rm.get_round_status()
        print(status["current_round"])
    """
    global _round_manager
    if _round_manager is None:
        _round_manager = RoundManager(state_file, expected_hospitals)
    return _round_manager
