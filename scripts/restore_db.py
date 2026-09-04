import os
import sys
import subprocess

def restore(backup_file):
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL environment variable is required to run restore.")
        return

    if not os.path.exists(backup_file):
        print(f"Error: Backup file {backup_file} not found.")
        return

    print(f"Starting restore from {backup_file}...")
    try:
        # First drop existing tables to ensure clean restore (Warning: Destructive!)
        # We assume the user is applying this over an empty DB or wants to overwrite.
        print("Restoring...")
        subprocess.run(
            ["psql", db_url, "-f", backup_file],
            check=True
        )
        print("Restore completed successfully!")
    except FileNotFoundError:
        print("Error: psql utility not found. Please ensure PostgreSQL client tools are installed.")
    except subprocess.CalledProcessError as e:
        print(f"Restore failed: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python restore_db.py <backup_file.sql>")
        sys.exit(1)
    restore(sys.argv[1])
