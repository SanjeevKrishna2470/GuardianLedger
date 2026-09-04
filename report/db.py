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
    conn = get_db()
    with conn:
        # Drop existing tables since we're changing the schema
        conn.execute("DROP TABLE IF EXISTS transactions")
        conn.execute("DROP TABLE IF EXISTS decisions")
        conn.execute("DROP TABLE IF EXISTS processed_events")
        conn.execute("DROP TABLE IF EXISTS users")
        conn.execute("DROP TABLE IF EXISTS merchants")

        # Create tables with multi-tenancy (merchant_id)
        conn.execute('''
            CREATE TABLE merchants (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                razorpay_key_id_enc TEXT,
                razorpay_key_secret_enc TEXT,
                razorpay_webhook_secret_enc TEXT
            )
        ''')
        conn.execute('''
            CREATE TABLE users (
                id TEXT PRIMARY KEY,
                merchant_id TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                FOREIGN KEY(merchant_id) REFERENCES merchants(id)
            )
        ''')
        conn.execute('''
            CREATE TABLE transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                merchant_id TEXT NOT NULL,
                timestamp TEXT,
                txn_ref TEXT NOT NULL,
                source TEXT,
                m1_match_result TEXT,
                m2_category TEXT,
                m3_extracted TEXT,
                m4_action TEXT,
                m4_reason TEXT,
                raw_evidence TEXT,
                FOREIGN KEY(merchant_id) REFERENCES merchants(id)
            )
        ''')
        conn.execute('''
            CREATE TABLE decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                merchant_id TEXT NOT NULL,
                timestamp TEXT,
                txn_ref TEXT,
                decision TEXT,
                reviewer_note TEXT,
                FOREIGN KEY(merchant_id) REFERENCES merchants(id)
            )
        ''')
        conn.execute('''
            CREATE TABLE processed_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                merchant_id TEXT NOT NULL,
                event_id TEXT,
                timestamp TEXT,
                FOREIGN KEY(merchant_id) REFERENCES merchants(id)
            )
        ''')
        
        # We also need a unique constraint on event_id + merchant_id, but the user requested unique constraint in Block 2. 
        # Actually, adding UNIQUE(event_id, merchant_id) now is better.
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_processed_events_unique ON processed_events(merchant_id, event_id)")
        
    conn.close()


# Initialise schema on import so every module that does `from report.db import ...`
# is guaranteed the tables exist.
init_db()
