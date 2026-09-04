import os
import re
import psycopg2
from psycopg2.extras import DictCursor

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class PostgresWrapper:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, query, params=None):
        # Convert SQLite ? placeholders to Postgres %s placeholders
        pg_query = query.replace("?", "%s")
        cur = self.conn.cursor(cursor_factory=DictCursor)
        cur.execute(pg_query, params)
        return cur
        
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.conn.commit()
        else:
            self.conn.rollback()

    def close(self):
        self.conn.close()

def get_db():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        # Fallback to sqlite if no Postgres URL is provided for local testing
        import sqlite3
        conn = sqlite3.connect(os.path.join(_PROJECT_ROOT, "data", "guardian_ledger.db"), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
        
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    return PostgresWrapper(conn)

def init_db():
    conn = get_db()
    if isinstance(conn, PostgresWrapper):
        with conn.conn.cursor() as cur:
            cur.execute('''
                CREATE TABLE IF NOT EXISTS merchants (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    razorpay_key_id_enc TEXT,
                    razorpay_key_secret_enc TEXT,
                    razorpay_webhook_secret_enc TEXT
                )
            ''')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL
                )
            ''')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS transactions (
                    id SERIAL PRIMARY KEY,
                    merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
                    timestamp TEXT,
                    txn_ref TEXT NOT NULL,
                    source TEXT,
                    m1_match_result TEXT,
                    m2_category TEXT,
                    m3_extracted TEXT,
                    m4_action TEXT,
                    m4_reason TEXT,
                    raw_evidence TEXT
                )
            ''')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS decisions (
                    id SERIAL PRIMARY KEY,
                    merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
                    timestamp TEXT,
                    txn_ref TEXT,
                    decision TEXT,
                    reviewer_note TEXT
                )
            ''')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS processed_events (
                    id SERIAL PRIMARY KEY,
                    merchant_id TEXT NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
                    event_id TEXT,
                    timestamp TEXT
                )
            ''')
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_processed_events_unique ON processed_events(merchant_id, event_id)")
        conn.conn.close()
    else:
        # SQLite initialization
        with conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS merchants (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    razorpay_key_id_enc TEXT,
                    razorpay_key_secret_enc TEXT,
                    razorpay_webhook_secret_enc TEXT
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    merchant_id TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL,
                    FOREIGN KEY(merchant_id) REFERENCES merchants(id)
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS transactions (
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
                CREATE TABLE IF NOT EXISTS decisions (
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
                CREATE TABLE IF NOT EXISTS processed_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    merchant_id TEXT NOT NULL,
                    event_id TEXT,
                    timestamp TEXT,
                    FOREIGN KEY(merchant_id) REFERENCES merchants(id)
                )
            ''')
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_processed_events_unique ON processed_events(merchant_id, event_id)")
        conn.close()

# Initialize when imported
init_db()
