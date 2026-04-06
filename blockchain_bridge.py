import json
import os
import logging
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(r"C:\\Users\\zvbrs\\Desktop\\Medledeger2\\.env")

logger = logging.getLogger(__name__)

SEPOLIA_URL  = "https://eth-sepolia.g.alchemy.com/v2/wtuVh2bMa4gsSARTR60ew"
PRIVATE_KEY  = "0x26d4ba413e34cb7da5ccbd9c68f46eaa35a53afdba835024aaa4f42a3b716019"
APP_ROOT     = os.path.dirname(os.path.abspath(__file__))
ADDRESS_FILE = os.path.join(APP_ROOT, "blockchain_address.json")
ABI_FILE     = os.path.join(APP_ROOT, "blockchain_abi.json")

_web3     = None
_contract = None
_account  = None

def _init():
    global _web3, _contract, _account
    if _contract is not None:
        return True
    try:
        from web3 import Web3, Account
        _web3 = Web3(Web3.HTTPProvider(SEPOLIA_URL))
        if not _web3.is_connected():
            logger.warning("[Blockchain] Cannot connect to Sepolia.")
            return False
        if not os.path.exists(ADDRESS_FILE):
            logger.warning("[Blockchain] blockchain_address.json not found.")
            return False
        with open(ADDRESS_FILE) as f:
            addr_data = json.load(f)
        contract_address = addr_data["address"]
        if not os.path.exists(ABI_FILE):
            logger.warning("[Blockchain] blockchain_abi.json not found.")
            return False
        with open(ABI_FILE) as f:
            abi = json.load(f)
        _contract = _web3.eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=abi
        )
        _account = Account.from_key(PRIVATE_KEY)
        logger.info(f"[Blockchain] Connected to Sepolia | contract={contract_address} | account={_account.address}")
        return True
    except ImportError:
        logger.warning("[Blockchain] web3 not installed. Run: pip install web3")
        return False
    except Exception as e:
        logger.warning(f"[Blockchain] Init failed: {str(e)}")
        return False

def _send_tx(fn):
    try:
        nonce = _web3.eth.get_transaction_count(_account.address)
        tx = fn.build_transaction({
            "from": _account.address,
            "nonce": nonce,
            "gas": 300000,
            "gasPrice": _web3.eth.gas_price,
        })
        signed = _web3.eth.account.sign_transaction(tx, PRIVATE_KEY)
        tx_hash = _web3.eth.send_raw_transaction(signed.raw_transaction)
        _web3.eth.wait_for_transaction_receipt(tx_hash)
        return tx_hash.hex()
    except Exception as e:
        logger.warning(f"[Blockchain] TX failed: {str(e)}")
        return None

def log_submission_event(hospital_id, round_num, weights_hash, accuracy, num_samples):
    if not _init():
        return {"success": False, "error": "Blockchain not available"}
    try:
        accuracy_x10000 = int(round(accuracy * 10000))
        fn = _contract.functions.logSubmission(
            hospital_id, round_num, weights_hash, accuracy_x10000, num_samples
        )
        tx = _send_tx(fn)
        logger.info(f"[Blockchain] Submission logged | hospital={hospital_id} | round={round_num}")
        return {"success": True, "tx_hash": tx}
    except Exception as e:
        logger.warning(f"[Blockchain] log_submission_event failed: {str(e)}")
        return {"success": False, "error": str(e)}

def log_aggregation_event(round_num, global_model_hash, hospitals, total_samples):
    if not _init():
        return {"success": False, "error": "Blockchain not available"}
    try:
        hospitals_str = ",".join(hospitals)
        fn = _contract.functions.logAggregation(
            round_num, global_model_hash, hospitals_str, total_samples
        )
        tx = _send_tx(fn)
        logger.info(f"[Blockchain] Aggregation logged | round={round_num}")
        return {"success": True, "tx_hash": tx}
    except Exception as e:
        logger.warning(f"[Blockchain] log_aggregation_event failed: {str(e)}")
        return {"success": False, "error": str(e)}

def log_login_event(hospital_id):
    if hospital_id == "admin":
        return {"success": True, "skipped": "admin logins not logged"}
    if not _init():
        return {"success": False, "error": "Blockchain not available"}
    try:
        fn = _contract.functions.logLogin(hospital_id)
        tx = _send_tx(fn)
        logger.info(f"[Blockchain] Login logged | hospital={hospital_id}")
        return {"success": True, "tx_hash": tx}
    except Exception as e:
        logger.warning(f"[Blockchain] log_login_event failed: {str(e)}")
        return {"success": False, "error": str(e)}

def get_all_events():
    if not _init():
        return []
    events = []
    try:
        count = _contract.functions.getSubmissionCount().call()
        for i in range(count):
            ev = _contract.functions.getSubmission(i).call()
            events.append({
                "type": "submission", "type_label": "Weight Submission", "type_color": "blue",
                "id": ev[0], "hospital_id": ev[1], "round_number": ev[2],
                "weights_hash": ev[3][:16] + "...", "weights_hash_full": ev[3],
                "accuracy": round(ev[4] / 10000, 4), "accuracy_pct": round(ev[4] / 100, 2),
                "num_samples": ev[5], "timestamp": ev[6], "timestamp_human": _ts_to_human(ev[6])
            })
        count = _contract.functions.getAggregationCount().call()
        for i in range(count):
            ev = _contract.functions.getAggregation(i).call()
            events.append({
                "type": "aggregation", "type_label": "FedAvg Aggregation", "type_color": "green",
                "id": ev[0], "round_number": ev[1],
                "global_model_hash": ev[2][:16] + "...", "global_model_hash_full": ev[2],
                "hospitals_list": ev[3], "total_samples": ev[4],
                "timestamp": ev[5], "timestamp_human": _ts_to_human(ev[5])
            })
        count = _contract.functions.getLoginCount().call()
        for i in range(count):
            ev = _contract.functions.getLogin(i).call()
            events.append({
                "type": "login", "type_label": "Hospital Login", "type_color": "gray",
                "id": ev[0], "hospital_id": ev[1],
                "timestamp": ev[2], "timestamp_human": _ts_to_human(ev[2])
            })
        events.sort(key=lambda x: x["timestamp"], reverse=True)
        return events
    except Exception as e:
        logger.warning(f"[Blockchain] get_all_events failed: {str(e)}")
        return []

def is_connected():
    return _init()

def _ts_to_human(unix_ts):
    try:
        return datetime.utcfromtimestamp(unix_ts).strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return str(unix_ts)
