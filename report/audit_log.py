import json
from datetime import datetime
import os

class AuditLogger:
    def __init__(self, log_file="data/audit_log.jsonl"):
        self.log_file = log_file
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        # Clear previous log for the run
        with open(self.log_file, 'w') as f:
            pass

    def log_transaction(self, txn_ref, match_result, category, extracted_data, action, reason):
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "txn_ref": txn_ref,
            "m1_match_result": match_result,
            "m2_category": category,
            "m3_extracted": extracted_data,
            "m4_action": action.name if hasattr(action, 'name') else action,
            "m4_reason": reason
        }
        with open(self.log_file, 'a') as f:
            f.write(json.dumps(entry) + '\n')

# Global instance for easy importing
logger = AuditLogger()
