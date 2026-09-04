import json
import os
import time

from report.db import get_db, _PROJECT_ROOT

def generate_report(merchant_id: str, start_time=None, end_time=None):
    conn = get_db()
    rows = conn.execute("SELECT m4_action, m2_category FROM transactions WHERE merchant_id = ?", (merchant_id,)).fetchall()
    conn.close()

    total = len(rows)
    matched = 0
    exceptions = {}
    quarantined = 0
    false_quarantine = 0

    for row in rows:
        action = row["m4_action"]
        cat = row["m2_category"]

        if action == "MATCH" or action == "POST":
            matched += 1
        elif action == "QUARANTINE":
            quarantined += 1
        elif action == "EXCEPTION" or cat:
            exceptions[cat] = exceptions.get(cat, 0) + 1

    throughput = 0
    if start_time and end_time:
        duration = end_time - start_time
        throughput = total / duration if duration > 0 else total

    report_data = {
        "total_processed": total,
        "match_rate": round((matched / total * 100), 2) if total > 0 else 0,
        "quarantine_count": quarantined,
        "false_quarantine_rate": round((false_quarantine / quarantined * 100), 2) if quarantined > 0 else 0,
        "throughput_records_per_sec": round(throughput, 2),
        "exception_breakdown": exceptions
    }
    
    return report_data
