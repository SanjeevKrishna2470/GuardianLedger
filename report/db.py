import sqlite3
import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(_PROJECT_ROOT, "data", "guardian_ledger.db")


def get_db() -> sqlite3.Connection:
    """Return a connection with row_factory set so rows behave like dicts."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create all tables if they don't already exist."""
    conn = get_db()
    with conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS transactions (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp       TEXT NOT NULL,
                txn_ref         TEXT NOT NULL,
                source          TEXT,
                m1_match_result TEXT,
                m2_category     TEXT,
                m3_extracted    TEXT,
                m4_action       TEXT,
                m4_reason       TEXT,
                raw_evidence    TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_txn_ref
                ON transactions(txn_ref);

            CREATE TABLE IF NOT EXISTS decisions (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp       TEXT NOT NULL,
                txn_ref         TEXT NOT NULL,
                decision        TEXT,
                reviewer_note   TEXT
            );

            CREATE TABLE IF NOT EXISTS processed_events (
                event_id        TEXT PRIMARY KEY,
                timestamp       TEXT NOT NULL
            );
        """)
    conn.close()


# Initialise schema on import so every module that does `from report.db import ...`
# is guaranteed the tables exist.
init_db()
