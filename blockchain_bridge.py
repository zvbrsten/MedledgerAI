"""
blockchain_bridge.py
====================
Python bridge between Flask and the local Hardhat blockchain.

Flask imports this module and calls:
    log_submission_event(...)
    log_aggregation_event(...)
    log_login_event(...)
    get_all_events()

This module reads:
    blockchain_address.json  ← created by deploy.js
    blockchain_abi.json      ← created by deploy.js

The Hardhat node must be running on localhost:8545.
If it is not running, all log_* calls silently fail (logged as warnings).
The Flask app continues to work — blockchain is audit layer, not critical path.
"""

import json
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# ── CONFIGURATION ─────────────────────────────────────────────────────────────

HARDHAT_URL     = "http://127.0.0.1:8545"
APP_ROOT        = os.path.dirname(os.path.abspath(__file__))
ADDRESS_FILE    = os.path.join(APP_ROOT, "blockchain_address.json")
ABI_FILE        = os.path.join(APP_ROOT, "blockchain_abi.json")

# ── LAZY INIT ─────────────────────────────────────────────────────────────────
# We don't crash if web3 is not installed or hardhat is not running.
# All functions return gracefully in that case.

_web3     = None
_contract = None
_account  = None


def _init():
    """
    Initialize web3 connection and contract instance.
    Called lazily on first use.
    Returns True if successful, False otherwise.
    """
    global _web3, _contract, _account

    if _contract is not None:
        return True  # Already initialized

    try:
        from web3 import Web3

        # Connect to local Hardhat node
        _web3 = Web3(Web3.HTTPProvider(HARDHAT_URL))
        if not _web3.is_connected():
            logger.warning(f"[Blockchain] Cannot connect to Hardhat at {HARDHAT_URL}. "
                           "Run 'npx hardhat node' in the blockchain/ folder.")
            return False

        # Load deployed contract address
        if not os.path.exists(ADDRESS_FILE):
            logger.warning(f"[Blockchain] {ADDRESS_FILE} not found. "
                           "Run deploy.js first.")
            return False

        with open(ADDRESS_FILE, "r") as f:
            addr_data = json.load(f)
        contract_address = addr_data["address"]

        # Load ABI
        if not os.path.exists(ABI_FILE):
            logger.warning(f"[Blockchain] {ABI_FILE} not found. "
                           "Run deploy.js first.")
            return False

        with open(ABI_FILE, "r") as f:
            abi = json.load(f)

        # Connect to contract
        _contract = _web3.eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=abi
        )

        # Use first Hardhat account as the transaction signer
        _account = _web3.eth.accounts[0]

        logger.info(f"[Blockchain] Connected | contract={contract_address} | account={_account}")
        return True

    except ImportError:
        logger.warning("[Blockchain] web3 not installed. Run: pip install web3")
        return False
    except Exception as e:
        logger.warning(f"[Blockchain] Init failed: {str(e)}")
        return False


# ── PUBLIC API ────────────────────────────────────────────────────────────────

def log_submission_event(
    hospital_id: str,
    round_num: int,
    weights_hash: str,
    accuracy: float,
    num_samples: int
) -> dict:
    """
    Log a hospital weight submission to the blockchain.

    Args:
        hospital_id:   e.g. "hospital_1"
        round_num:     FL round number
        weights_hash:  SHA-256 hex string of weights.pt
        accuracy:      float 0.0–1.0
        num_samples:   number of training samples

    Returns:
        {"success": True, "tx_hash": "0x..."} or {"success": False, "error": "..."}
    """
    if not _init():
        return {"success": False, "error": "Blockchain not available"}

    try:
        accuracy_x10000 = int(round(accuracy * 10000))
        tx_hash = _contract.functions.logSubmission(
            hospital_id,
            round_num,
            weights_hash,
            accuracy_x10000,
            num_samples
        ).transact({"from": _account})

        _web3.eth.wait_for_transaction_receipt(tx_hash)
        tx_str = tx_hash.hex()
        logger.info(
            f"[Blockchain] Submission logged | hospital={hospital_id} | "
            f"round={round_num} | tx={tx_str[:20]}..."
        )
        return {"success": True, "tx_hash": tx_str}

    except Exception as e:
        logger.warning(f"[Blockchain] log_submission_event failed: {str(e)}")
        return {"success": False, "error": str(e)}


def log_aggregation_event(
    round_num: int,
    global_model_hash: str,
    hospitals: list,
    total_samples: int
) -> dict:
    """
    Log a FedAvg aggregation completion to the blockchain.

    Args:
        round_num:          FL round number
        global_model_hash:  SHA-256 hex string of global_model_roundN.pt
        hospitals:          list of hospital IDs that participated
        total_samples:      total training samples across all hospitals

    Returns:
        {"success": True, "tx_hash": "0x..."} or {"success": False, "error": "..."}
    """
    if not _init():
        return {"success": False, "error": "Blockchain not available"}

    try:
        hospitals_str = ",".join(hospitals)
        tx_hash = _contract.functions.logAggregation(
            round_num,
            global_model_hash,
            hospitals_str,
            total_samples
        ).transact({"from": _account})

        _web3.eth.wait_for_transaction_receipt(tx_hash)
        tx_str = tx_hash.hex()
        logger.info(
            f"[Blockchain] Aggregation logged | round={round_num} | "
            f"hospitals={hospitals_str} | tx={tx_str[:20]}..."
        )
        return {"success": True, "tx_hash": tx_str}

    except Exception as e:
        logger.warning(f"[Blockchain] log_aggregation_event failed: {str(e)}")
        return {"success": False, "error": str(e)}


def log_login_event(hospital_id: str) -> dict:
    """
    Log a hospital login to the blockchain.

    Args:
        hospital_id:  Hospital identifier (skip admin logins)

    Returns:
        {"success": True, "tx_hash": "0x..."} or {"success": False, "error": "..."}
    """
    if hospital_id == "admin":
        return {"success": True, "skipped": "admin logins not logged"}

    if not _init():
        return {"success": False, "error": "Blockchain not available"}

    try:
        tx_hash = _contract.functions.logLogin(hospital_id).transact({"from": _account})
        _web3.eth.wait_for_transaction_receipt(tx_hash)
        tx_str = tx_hash.hex()
        logger.info(f"[Blockchain] Login logged | hospital={hospital_id} | tx={tx_str[:20]}...")
        return {"success": True, "tx_hash": tx_str}

    except Exception as e:
        logger.warning(f"[Blockchain] log_login_event failed: {str(e)}")
        return {"success": False, "error": str(e)}


def get_all_events() -> list:
    """
    Fetch all logged events from the blockchain.
    Returns a unified list sorted by timestamp, newest first.
    Each event has: type, timestamp, timestamp_human, and event-specific fields.

    Returns:
        List of event dicts ready for the blockchain_ledger.html template.
    """
    if not _init():
        return []

    events = []

    try:
        # ── Submission events ─────────────────────────────────────────────────
        count = _contract.functions.getSubmissionCount().call()
        for i in range(count):
            ev = _contract.functions.getSubmission(i).call()
            events.append({
                "type":            "submission",
                "type_label":      "Weight Submission",
                "type_color":      "blue",
                "id":              ev[0],
                "hospital_id":     ev[1],
                "round_number":    ev[2],
                "weights_hash":    ev[3][:16] + "...",  # truncated for display
                "weights_hash_full": ev[3],
                "accuracy":        round(ev[4] / 10000, 4),
                "accuracy_pct":    round(ev[4] / 100, 2),
                "num_samples":     ev[5],
                "timestamp":       ev[6],
                "timestamp_human": _ts_to_human(ev[6])
            })

        # ── Aggregation events ────────────────────────────────────────────────
        count = _contract.functions.getAggregationCount().call()
        for i in range(count):
            ev = _contract.functions.getAggregation(i).call()
            events.append({
                "type":              "aggregation",
                "type_label":        "FedAvg Aggregation",
                "type_color":        "green",
                "id":                ev[0],
                "round_number":      ev[1],
                "global_model_hash": ev[2][:16] + "...",
                "global_model_hash_full": ev[2],
                "hospitals_list":    ev[3],
                "total_samples":     ev[4],
                "timestamp":         ev[5],
                "timestamp_human":   _ts_to_human(ev[5])
            })

        # ── Login events ──────────────────────────────────────────────────────
        count = _contract.functions.getLoginCount().call()
        for i in range(count):
            ev = _contract.functions.getLogin(i).call()
            events.append({
                "type":            "login",
                "type_label":      "Hospital Login",
                "type_color":      "gray",
                "id":              ev[0],
                "hospital_id":     ev[1],
                "timestamp":       ev[2],
                "timestamp_human": _ts_to_human(ev[2])
            })

        # Sort newest first
        events.sort(key=lambda x: x["timestamp"], reverse=True)
        return events

    except Exception as e:
        logger.warning(f"[Blockchain] get_all_events failed: {str(e)}")
        return []


def is_connected() -> bool:
    """Check if blockchain bridge is active. Used by status endpoints."""
    return _init()


# ── HELPERS ───────────────────────────────────────────────────────────────────

def _ts_to_human(unix_ts: int) -> str:
    """Convert Unix timestamp to readable string."""
    try:
        return datetime.utcfromtimestamp(unix_ts).strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return str(unix_ts)