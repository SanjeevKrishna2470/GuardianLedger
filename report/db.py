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
            _init_block3_tables(conn, is_pg=True)
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
            _init_block3_tables(conn, is_pg=False)
        conn.close()

def _init_block3_tables(conn, is_pg: bool):
    """Stateful ledger, unmatched bank pile, and retroactive-correction audit."""
    id_col = "SERIAL PRIMARY KEY" if is_pg else "INTEGER PRIMARY KEY AUTOINCREMENT"
    conn.execute(f'''
        CREATE TABLE IF NOT EXISTS payments_ledger (
            merchant_id TEXT NOT NULL,
            payment_id TEXT NOT NULL,
            order_id TEXT,
            amount REAL,
            currency TEXT,
            status TEXT NOT NULL,
            match_status TEXT NOT NULL DEFAULT 'UNMATCHED',
            exception_flag TEXT,
            priority INTEGER DEFAULT 0,
            unmatched_since TEXT,
            authorized_at TEXT,
            captured_at TEXT,
            settled_at TEXT,
            created_at TEXT,
            updated_at TEXT,
            PRIMARY KEY (merchant_id, payment_id)
        )
    ''')
    conn.execute(f'''
        CREATE TABLE IF NOT EXISTS bank_statement_lines (
            id {id_col},
            merchant_id TEXT NOT NULL,
            external_id TEXT,
            txn_ref TEXT,
            amount REAL,
            value_date TEXT,
            fee_deducted REAL DEFAULT 0,
            description TEXT,
            match_status TEXT NOT NULL DEFAULT 'UNMATCHED',
            matched_payment_id TEXT,
            created_at TEXT,
            UNIQUE (merchant_id, external_id)
        )
    ''')
    conn.execute(f'''
        CREATE TABLE IF NOT EXISTS reconciliation_corrections (
            id {id_col},
            merchant_id TEXT NOT NULL,
            payment_id TEXT NOT NULL,
            old_status TEXT,
            new_status TEXT,
            old_match_status TEXT,
            new_match_status TEXT,
            old_amount REAL,
            new_amount REAL,
            reason TEXT,
            timestamp TEXT
        )
    ''')
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ledger_unmatched ON payments_ledger(merchant_id, match_status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bank_unmatched ON bank_statement_lines(merchant_id, match_status)")
    _add_column_if_missing(conn, "transactions", "priority", "INTEGER DEFAULT 0", is_pg)


def _add_column_if_missing(conn, table, column, coltype, is_pg: bool):
    if is_pg:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {coltype}")
        return
    cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
    names = {row["name"] for row in cols}
    if column not in names:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")


# Initialize when imported
init_db()
