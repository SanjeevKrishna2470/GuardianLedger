import json
import os
import sys

from report.db import get_db, init_db, _PROJECT_ROOT

DATA_DIR = os.path.join(_PROJECT_ROOT, "data")


def migrate_audit_log():
    jsonl_path = os.path.join(DATA_DIR, "audit_log.jsonl")
    if not os.path.exists(jsonl_path):
        print("No audit_log.jsonl found. Skipping.")
        return 0

    conn = get_db()
    count = 0
    with open(jsonl_path, "r") as f:
        with conn:
            for line in f:
                if not line.strip():
                    continue
                entry = json.loads(line)
                conn.execute(
                    """
                    INSERT INTO transactions
                        (timestamp, txn_ref, source,
                         m1_match_result, m2_category, m3_extracted,
                         m4_action, m4_reason, raw_evidence)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry.get("timestamp"),
                        entry.get("txn_ref"),
                        entry.get("source"),
                        entry.get("m1_match_result"),
                        entry.get("m2_category"),
                        json.dumps(entry.get("m3_extracted")) if entry.get("m3_extracted") is not None else None,
                        entry.get("m4_action"),
                        entry.get("m4_reason"),
                        json.dumps(entry.get("raw_evidence")) if entry.get("raw_evidence") is not None else None,
                    ),
                )
                count += 1
    conn.close()
    return count


def migrate_decisions():
    jsonl_path = os.path.join(DATA_DIR, "decisions.jsonl")
    if not os.path.exists(jsonl_path):
        print("No decisions.jsonl found. Skipping.")
        return 0

    conn = get_db()
    count = 0
    with open(jsonl_path, "r") as f:
        with conn:
            for line in f:
                if not line.strip():
                    continue
                entry = json.loads(line)
                conn.execute(
                    "INSERT INTO decisions (timestamp, txn_ref, decision, reviewer_note) VALUES (?, ?, ?, ?)",
                    ("2024-01-01T00:00:00", entry.get("txn_ref"), entry.get("decision"), entry.get("reviewer_note")),
                )
                count += 1
    conn.close()
    return count


def migrate_processed_events():
    jsonl_path = os.path.join(DATA_DIR, "processed_event_ids.jsonl")
    if not os.path.exists(jsonl_path):
        print("No processed_event_ids.jsonl found. Skipping.")
        return 0

    conn = get_db()
    count = 0
    with open(jsonl_path, "r") as f:
        with conn:
            for line in f:
                if not line.strip():
                    continue
                entry = json.loads(line)
                # Use INSERT OR IGNORE just in case there are duplicates in the JSONL
                conn.execute(
                    "INSERT OR IGNORE INTO processed_events (event_id, timestamp) VALUES (?, ?)",
                    (entry.get("event_id"), entry.get("timestamp")),
                )
                count += 1
    conn.close()
    return count


def main():
    print("Initialising SQLite database schema...")
    init_db()

    print("Migrating audit_log.jsonl...")
    audit_count = migrate_audit_log()
    print(f"Migrated {audit_count} transactions.")

    print("Migrating decisions.jsonl...")
    decisions_count = migrate_decisions()
    print(f"Migrated {decisions_count} decisions.")

    print("Migrating processed_event_ids.jsonl...")
    events_count = migrate_processed_events()
    print(f"Migrated {events_count} processed events.")

    print("\nMigration complete! You can now safely remove the old .jsonl files in the data/ folder.")


if __name__ == "__main__":
    main()
