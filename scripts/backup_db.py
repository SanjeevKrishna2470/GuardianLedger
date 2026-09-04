import os
import subprocess
from datetime import datetime

def backup():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL environment variable is required to run backups.")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"backup_{timestamp}.sql"
    
    print(f"Starting backup to {backup_file}...")
    try:
        subprocess.run(
            ["pg_dump", db_url, "-f", backup_file],
            check=True
        )
        print("Backup completed successfully!")
    except FileNotFoundError:
        print("Error: pg_dump utility not found. Please ensure PostgreSQL client tools are installed.")
    except subprocess.CalledProcessError as e:
        print(f"Backup failed: {e}")

if __name__ == "__main__":
    backup()
