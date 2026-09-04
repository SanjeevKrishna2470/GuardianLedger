import json
import os
import time

from report.db import get_db, _PROJECT_ROOT

def generate_report(start_time=None, end_time=None):
    conn = get_db()
    rows = conn.execute("SELECT m4_action, m2_category FROM transactions").fetchall()
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
        "match_rate": (matched / total * 100) if total > 0 else 0,
        "quarantine_count": quarantined,
        "false_quarantine_rate": (false_quarantine / quarantined * 100) if quarantined > 0 else 0,
        "throughput_records_per_sec": throughput,
        "exception_breakdown": exceptions
    }
    
    # Write JSON report
    with open(os.path.join(_PROJECT_ROOT, "data", "report.json"), 'w') as f:
        json.dump(report_data, f, indent=2)
        
    # Write Markdown summary
    md = f"""# Guardian Ledger Run Report

## Headline Numbers
- **Match Rate**: {report_data['match_rate']:.2f}% ({matched}/{total})
- **Quarantined**: {quarantined} (False quarantine rate: {report_data['false_quarantine_rate']:.2f}%)
- **Throughput**: {throughput:.2f} records/sec

## Exception Breakdown
"""
    for k, v in exceptions.items():
        md += f"- **{k}**: {v}\n"
        
    with open(os.path.join(_PROJECT_ROOT, "data", "report.md"), 'w') as f:
        f.write(md)
        
    print(md)
