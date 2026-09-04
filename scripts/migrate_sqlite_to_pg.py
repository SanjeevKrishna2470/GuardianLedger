import os
import sqlite3
import psycopg2

def migrate():
    sqlite_db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "guardian_ledger.db")
    pg_url = os.environ.get("DATABASE_URL")
    
    if not os.path.exists(sqlite_db_path):
        print(f"SQLite DB not found at {sqlite_db_path}")
        return
        
    if not pg_url:
        print("DATABASE_URL is not set. Migration requires a target Postgres database.")
        return
        
    print("Connecting to SQLite...")
    sqlite_conn = sqlite3.connect(sqlite_db_path)
    sqlite_conn.row_factory = sqlite3.Row
    
    print("Connecting to Postgres...")
    pg_conn = psycopg2.connect(pg_url)
    
    tables = ["merchants", "users", "transactions", "decisions", "processed_events"]
    
    with pg_conn.cursor() as cur:
        for table in tables:
            print(f"Migrating table: {table}...")
            rows = sqlite_conn.execute(f"SELECT * FROM {table}").fetchall()
            
            if not rows:
                print(f"  No rows in {table}.")
                continue
                
            cols = rows[0].keys()
            placeholders = ",".join(["%s"] * len(cols))
            col_names = ",".join(cols)
            
            insert_query = f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})"
            
            for row in rows:
                cur.execute(insert_query, tuple(row))
                
            print(f"  Inserted {len(rows)} rows into {table}.")
            
    pg_conn.commit()
    sqlite_conn.close()
    pg_conn.close()
    print("Migration complete!")

if __name__ == "__main__":
    migrate()
