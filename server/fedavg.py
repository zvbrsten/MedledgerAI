"""
========================================================================
FEDERATED AVERAGING (FedAvg) - Server-Side Aggregation Module
========================================================================

ARCHITECTURAL PRINCIPLE:
    "Hospitals train. Server aggregates. Website observes."

This module is RESPONSIBLE ONLY for:
    1. Loading trained model weights from hospitals
    2. Computing weighted average (FedAvg)
    3. Saving aggregated global model

This module is NOT responsible for:
    1. Accessing patient data (hospitals keep this)
    2. Triggering training (hospitals do this independently)
    3. Running PyTorch training (PyTorch is stateless here)

SECURITY & PRIVACY GUARANTEES:
    ✓ Server never sees patient data
    ✓ Server only handles .pt files (model weights)
    ✓ Server never executes hospital training code
    ✓ Hospital remains sole owner of its data
    ✓ Aggregation is pure mathematical averaging
"""

import os
import logging
from typing import Dict, List, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

# Lazy import torch only when needed
try:
    import torch
except ImportError:
    torch = None


class FedAvgAggregator:
    """
    Pure aggregation engine for Federated Learning.
    
    Performs weighted averaging of model weights:
        global_model = mean(local_models, weighted by sample counts)
    
    No data processing. No training. Only aggregation.
    """
    
    def __init__(self, model_class=None):
        """
        Initialize aggregator.
        
        Args:
            model_class: PyTorch model class (e.g., ResNet18)
                        If None, aggregation works with raw state dicts
        """
        self.model_class = model_class
        self.logger = logging.getLogger(f"{__name__}.FedAvgAggregator")
    
    def aggregate(
        self,
        submissions: Dict[str, Tuple[str, int]],
        global_round: int,
        output_dir: str = "models/global"
    ) -> Tuple[bool, str, dict]:
        """
        Perform FedAvg aggregation across all hospital submissions.
        
        CRITICAL SECURITY NOTE:
            This function:
            ✓ Reads .pt files (model parameters only)
            ✓ Performs weighted averaging
            ✓ Writes aggregated .pt file
            ✗ Never accesses patient data
            ✗ Never executes training
            ✗ Never modifies original hospital files
        
        Args:
            submissions: Dict mapping hospital_id -> (weights_filepath, num_samples)
                        Example: {
                            "hospital_1": ("weights/local_model_round1.pt", 500),
                            "hospital_2": ("weights/local_model_round1.pt", 450),
                        }
            global_round: Current federated learning round number
            output_dir: Directory to save global_model_roundN.pt
        
        Returns:
            (success: bool, message: str, metadata: dict)
        """
        
        if torch is None:
            return False, "PyTorch not available. Cannot perform aggregation.", {"error": "torch_unavailable"}
        
        try:
            self.logger.info(f"[FedAvg] Starting aggregation for Round {global_round}")
            self.logger.info(f"[FedAvg] Submissions from {len(submissions)} hospitals")
            
            # ====================================================================
            # STEP 1: Validate all submissions exist
            # ====================================================================
            missing_files = []
            total_samples = 0
            
            for hospital_id, (weight_path, num_samples) in submissions.items():
                if not os.path.exists(weight_path):
                    missing_files.append(f"{hospital_id}: {weight_path}")
                else:
                    total_samples += num_samples
                    self.logger.debug(f"  ✓ {hospital_id}: {num_samples} samples")
            
            if missing_files:
                msg = f"Missing weight files: {', '.join(missing_files)}"
                self.logger.error(f"[FedAvg] {msg}")
                return False, msg, {"error": msg}
            
            self.logger.info(f"[FedAvg] Total samples across all hospitals: {total_samples}")
            
            # ====================================================================
            # STEP 2: Load all hospital model weights
            # ====================================================================
            hospital_weights = {}
            
            for hospital_id, (weight_path, num_samples) in submissions.items():
                try:
                    state_dict = torch.load(weight_path, map_location='cpu')
                    hospital_weights[hospital_id] = {
                        'state_dict': state_dict,
                        'num_samples': num_samples,
                        'weight': num_samples / total_samples  # Sample-weighted proportion
                    }
                    self.logger.debug(f"  ✓ Loaded {hospital_id} (weight={num_samples/total_samples:.2%})")
                except Exception as e:
                    msg = f"Failed to load weights from {hospital_id}: {str(e)}"
                    self.logger.error(f"[FedAvg] {msg}")
                    return False, msg, {"error": msg, "hospital": hospital_id}
            
            # ====================================================================
            # STEP 3: Perform FedAvg aggregation (weighted averaging)
            # ====================================================================
            self.logger.info("[FedAvg] Computing weighted average...")
            
            # Get first hospital's state dict as template
            first_hospital_id = list(hospital_weights.keys())[0]
            template_state = hospital_weights[first_hospital_id]['state_dict']
            
            # Initialize aggregated state dict with zeros
            aggregated_state = {}
            
            for param_name in template_state.keys():
                aggregated_state[param_name] = torch.zeros_like(
                    template_state[param_name],
                    dtype=torch.float32
                )
            
            # Compute weighted sum
            for hospital_id, data in hospital_weights.items():
                weight = data['weight']
                state_dict = data['state_dict']
                
                for param_name, param in state_dict.items():
                    # Weighted contribution of this hospital to global model
                    aggregated_state[param_name] += weight * param.float()
            
            self.logger.info("[FedAvg] ✓ Weighted averaging complete")
            
            # ====================================================================
            # STEP 4: Save aggregated global model
            # ====================================================================
            os.makedirs(output_dir, exist_ok=True)
            
            global_model_path = os.path.join(
                output_dir,
                f"global_model_round{global_round}.pt"
            )
            
            try:
                torch.save(aggregated_state, global_model_path)
                file_size = os.path.getsize(global_model_path) / (1024 * 1024)
                self.logger.info(f"[FedAvg] ✓ Global model saved: {global_model_path}")
                self.logger.info(f"[FedAvg]   File size: {file_size:.2f} MB")
            except Exception as e:
                msg = f"Failed to save global model: {str(e)}"
                self.logger.error(f"[FedAvg] {msg}")
                return False, msg, {"error": msg}
            
            # ====================================================================
            # STEP 5: Return aggregation metadata
            # ====================================================================
            metadata = {
                "round": global_round,
                "aggregated_hospitals": list(hospital_weights.keys()),
                "total_hospitals": len(hospital_weights),
                "total_samples": total_samples,
                "global_model_path": global_model_path,
                "file_size_mb": file_size,
                "aggregation_method": "FedAvg (weighted by sample count)"
            }
            
            self.logger.info(f"[FedAvg] ✓ Aggregation complete for Round {global_round}")
            self.logger.info(f"[FedAvg]   Hospitals: {', '.join(hospital_weights.keys())}")
            self.logger.info(f"[FedAvg]   Total samples: {total_samples}")
            
            return True, f"Aggregation successful for round {global_round}", metadata
        
        except Exception as e:
            error_msg = f"Unexpected error during aggregation: {str(e)}"
            self.logger.exception(error_msg)
            return False, error_msg, {"error": error_msg}
    
    def verify_aggregation(self, global_model_path: str) -> bool:
        """
        Verify that aggregated model was saved correctly.
        
        Args:
            global_model_path: Path to global_model_roundN.pt
        
        Returns:
            True if file exists and can be loaded, False otherwise
        """
        try:
            if not os.path.exists(global_model_path):
                self.logger.warning(f"Global model not found: {global_model_path}")
                return False
            
            # Try to load to verify integrity (if torch available)
            if torch is not None:
                state_dict = torch.load(global_model_path, map_location='cpu')
                self.logger.debug(f"✓ Verified aggregated model: {global_model_path}")
            else:
                # Without torch, just check file exists and has content
                file_size = os.path.getsize(global_model_path)
                if file_size > 0:
                    self.logger.debug(f"✓ Model file exists (torch not available for detailed check): {global_model_path}")
                else:
                    self.logger.warning(f"Model file is empty: {global_model_path}")
                    return False
            
            return True
        except Exception as e:
            self.logger.error(f"Failed to verify model: {str(e)}")
            return False


def aggregate_round(submissions: Dict[str, Tuple[str, int]], round_num: int) -> Tuple[bool, str, dict]:
    """
    Convenience function to perform aggregation in one call.
    
    USAGE:
        success, msg, metadata = aggregate_round({
            "hospital_1": ("models/hospital_1/local_model_round1.pt", 500),
            "hospital_2": ("models/hospital_2/local_model_round1.pt", 450),
            "hospital_3": ("models/hospital_3/local_model_round1.pt", 480),
        }, round_num=1)
        
        if success:
            print(f"Global model: {metadata['global_model_path']}")
    
    Args:
        submissions: Hospital submissions mapping
        round_num: Current round number
    
    Returns:
        (success, message, metadata)
    """
    aggregator = FedAvgAggregator()
    return aggregator.aggregate(submissions, round_num)
