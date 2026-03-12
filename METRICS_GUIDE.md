# Federated Learning Metrics & Continuous Logging System

## Overview

The MedLedger-AI system implements a comprehensive metrics tracking system that logs the entire journey of model improvement as hospitals participate in federated learning rounds. Every round of training creates permanent records that track model performance across multiple dimensions.

## Key Metrics Explained

### Classification Metrics

#### **Accuracy** (Overall Correctness)
- **Range:** 0-100%
- **Formula:** (Correct Predictions) / (Total Predictions)
- **Interpretation:** Percentage of correct predictions across all classes
- **Medical Context:** Overall model reliability
- **Current Value:** 89.50%

#### **Precision** (False Positive Rate)
- **Range:** 0-100%
- **Formula:** (True Positives) / (True Positives + False Positives)
- **Interpretation:** Of all positive diagnoses, how many were correct
- **Medical Context:** Critical for avoiding unnecessary treatments
- **Current Value:** 87.20%

#### **Recall (Sensitivity)** (False Negative Rate)
- **Range:** 0-100%
- **Formula:** (True Positives) / (True Positives + False Negatives)
- **Interpretation:** Of all actual disease cases, how many were detected
- **Medical Context:** Critical for not missing diagnoses
- **Current Value:** 90.20%

#### **F1 Score** (Harmonic Mean)
- **Range:** 0-1.0
- **Formula:** 2 × (Precision × Recall) / (Precision + Recall)
- **Interpretation:** Balanced metric considering both precision and recall
- **Medical Context:** Optimal when both false positives and false negatives matter
- **Current Value:** 0.8860

#### **AUC-ROC** (Discrimination Ability)
- **Range:** 0-100%
- **Interpretation:** Model's ability to distinguish between classes across all thresholds
- **Medical Context:** Measures diagnostic capability independent of decision threshold
- **Current Value:** 92.10%

#### **Loss** (Training Error)
- **Range:** 0-∞ (typically 0-1)
- **Interpretation:** Lower values indicate better model fit
- **Medical Context:** Indicates convergence of training process
- **Current Value:** 0.2450 (decreasing over rounds = improving)

## Continuous Logging Architecture

### Data Structure

The metrics are stored in `/data/federated_metrics.json` with the following structure:

```json
{
  "model_id": "medledger_global_v1",
  "last_updated": "ISO 8601 timestamp",
  "institutions_participated": 5,
  "training_rounds": 10,
  
  // Per-round metrics (arrays, one entry per round)
  "accuracy_per_round": [0.71, 0.734, ...],
  "precision_per_round": [0.685, 0.71, ...],
  "recall_per_round": [0.72, 0.745, ...],
  "f1_score_per_round": [0.702, 0.727, ...],
  "loss_per_round": [0.68, 0.61, ...],
  "auc_roc_per_round": [0.765, 0.789, ...],
  
  // Final metrics
  "final_accuracy": 89.50,
  "final_precision": 87.20,
  "final_recall": 90.20,
  "final_f1_score": 0.8860,
  "final_loss": 0.2450,
  "final_auc_roc": 92.10,
  
  // Training history log
  "training_history": [
    {
      "round": 1,
      "timestamp": "2026-01-25T08:00:00",
      "institutions_participated": 3,
      "samples_processed": 15420,
      "accuracy": 0.71,
      "precision": 0.685,
      "recall": 0.72,
      "f1_score": 0.702,
      "loss": 0.68,
      "auc_roc": 0.765
    },
    ...
  ]
}
```

## How Continuous Logging Works

### 1. **Initial Training (Round 1)**
- Model trains on data from 3 hospitals
- Metrics are computed and stored in arrays
- Entry added to `training_history` for permanent record
- Timestamps capture exact time of completion

### 2. **Hospital Contribution (Round N)**
- New hospital contributes dataset
- Federated learning orchestrator runs training on global model
- Model improves (metrics increase or loss decreases)
- New values **appended** to per-round arrays
- **New history entry** created for this round
- `last_updated` timestamp updated
- All previous rounds remain unchanged

### 3. **Continuous Journey**
- As more hospitals join (Round 3: 5 institutions)
- Model accumulates knowledge from diverse data sources
- Metrics show improvement trajectory
- Historical data never deleted - complete audit trail maintained
- Website displays full journey of improvement

## Using the Metrics System

### Viewing Current Metrics

Navigate to **Admin Console** → **Federated Training Status** to view:
- **Key Metrics Panel:** Current accuracy, precision, recall, F1, AUC-ROC, loss
- **Training Progress Charts:** Line charts showing trend for each metric
- **Complete Comparison Chart:** All metrics overlaid for pattern analysis
- **Training Journey Table:** Full history of every round with details

### Appending New Training Rounds

When a federated learning round completes, append metrics using:

```bash
python append_metrics_round.py \
  --round 11 \
  --accuracy 0.895 \
  --precision 0.878 \
  --recall 0.912 \
  --f1 0.895 \
  --loss 0.219 \
  --auc 0.924 \
  --institutions 6 \
  --samples 22000
```

### Automatic Logging

For integration with Jupyter notebook exports:

1. **Notebook exports** metrics after each training round to `/exports/federated_metrics.json`
2. **Website imports** from `/data/federated_metrics.json`
3. **Manual append** using `append_metrics_round.py` or API endpoint
4. **Continuous tracking** maintains unbroken history

## Interpreting Improvement Patterns

### Healthy Model Improvement
- ✅ Accuracy increasing across rounds
- ✅ Loss decreasing across rounds
- ✅ Precision + Recall increasing
- ✅ AUC-ROC improving
- ✅ F1 Score converging

### Metrics Plateauing
- May indicate model has learned maximum from available data
- More diverse hospitals/datasets needed
- Feature engineering improvements possible
- Model architecture optimization required

### Metrics Degrading
- May indicate overfitting to one hospital's data
- Regularization increased
- Reduce learning rate
- Add data augmentation

## Integration Points

### For Notebook (Training Side)
```python
# At end of each FL round:
metrics = {
    'model_id': 'medledger_global_v1',
    'last_updated': datetime.now().isoformat(),
    'training_rounds': current_round,
    'accuracy_per_round': accuracies,  # Full array
    'precision_per_round': precisions,
    'recall_per_round': recalls,
    'f1_score_per_round': f1_scores,
    'loss_per_round': losses,
    'auc_roc_per_round': auc_rocs,
    'final_accuracy': current_accuracy * 100,
    'training_history': [...]  # Append new entry
}
json.dump(metrics, file)
```

### For Website (Display Side)
- Reads from `/data/federated_metrics.json`
- Template renders all per-round arrays as charts
- Training history displayed as scrollable table
- Read-only - no modifications from website

## Best Practices

1. **Export After Each Round:** Always append metrics after training completes
2. **Timestamp Consistency:** Use ISO 8601 format for all timestamps
3. **Array Alignment:** Ensure all per-round arrays have same length
4. **History Preservation:** Never delete training_history entries
5. **Backup Regularly:** Version control or backup metrics JSON
6. **Validate Data:** Check metrics are within expected ranges (0-1 for scores, 0+ for loss)

## Future Enhancements

- ✅ Currently: Full metrics per round + history log
- 🔄 Planned: Real-time updates as training progresses
- 🔄 Planned: Comparative analysis across hospitals
- 🔄 Planned: Automated alert if metrics degrade
- 🔄 Planned: Export reports as PDF

## Technical Details

**Files Involved:**
- `/data/federated_metrics.json` - Main metrics storage
- `/templates/model_status.html` - Display interface
- `/app.py` - Flask route `/model-status`
- `/metrics_loader.py` - JSON parsing utility
- `/append_metrics_round.py` - Utility for appending new rounds

**Update Frequency:** On-demand after each FL round
**Retention:** Permanent (until explicitly archived)
**Access:** Read-only from website, write-only from training system
