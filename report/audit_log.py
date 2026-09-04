import json
from datetime import datetime
import os

# Anchor the project root to the directory two levels above this file:
# report/audit_log.py  ->  report/  ->  <project_root>/
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class AuditLogger:
    def __init__(self, log_file=None):
        if log_file is None:
            # Always resolve relative to the project root, not the CWD.
            log_file = os.path.join(_PROJECT_ROOT, "data", "audit_log.jsonl")
        self.log_file = log_file
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        # Touch file if it doesn't exist
        if not os.path.exists(self.log_file):
            with open(self.log_file, 'w') as f:
                pass

    def log_transaction(self, txn_ref, match_result, category, extracted_data, action, reason, source="BATCH_PIPELINE", raw_evidence=None):
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "txn_ref": txn_ref,
            "source": source,
            "m1_match_result": match_result,
            "m2_category": category,
            "m3_extracted": extracted_data,
            "m4_action": action.name if hasattr(action, 'name') else str(action),
            "m4_reason": reason,
            "raw_evidence": raw_evidence or {}
        }
        with open(self.log_file, 'a') as f:
            f.write(json.dumps(entry) + '\n')

# Global instance for easy importing
logger = AuditLogger()
