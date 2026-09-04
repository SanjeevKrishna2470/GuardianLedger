import json
from datetime import datetime

from report.db import get_db


class AuditLogger:
    def log_transaction(
        self,
        txn_ref,
        match_result,
        category,
        extracted_data,
        action,
        reason,
        source="BATCH_PIPELINE",
        raw_evidence=None,
    ):
        conn = get_db()
        with conn:
            conn.execute(
                """
                INSERT INTO transactions
                    (timestamp, txn_ref, source,
                     m1_match_result, m2_category, m3_extracted,
                     m4_action, m4_reason, raw_evidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.utcnow().isoformat(),
                    txn_ref,
                    source,
                    match_result,
                    category,
                    json.dumps(extracted_data) if extracted_data is not None else None,
                    action.name if hasattr(action, "name") else str(action),
                    reason,
                    json.dumps(raw_evidence) if raw_evidence is not None else None,
                ),
            )
        conn.close()

    def is_logged(self, txn_ref: str) -> bool:
        """Return True if a transaction with this txn_ref already exists in the DB."""
        conn = get_db()
        row = conn.execute(
            "SELECT 1 FROM transactions WHERE txn_ref = ? LIMIT 1", (txn_ref,)
        ).fetchone()
        conn.close()
        return row is not None


# Global instance for easy importing
logger = AuditLogger()

