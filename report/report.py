import json
import os
import time

def generate_report(log_file="data/audit_log.jsonl", start_time=None, end_time=None):
    total = 0
    matched = 0
    exceptions = {}
    quarantined = 0
    false_quarantine = 0 # In a real scenario, this would be computed against truth labels
    
    with open(log_file, 'r') as f:
        for line in f:
            if not line.strip():
                continue
            entry = json.loads(line)
            total += 1
            
            action = entry.get("m4_action")
            cat = entry.get("m2_category")
            
            if action == "MATCH" or action == "POST":
                matched += 1
            elif action == "QUARANTINE":
                quarantined += 1
                # If it's a known clean txn that got quarantined
                if "true_category" in entry and entry["true_category"] == "CLEAN":
                    false_quarantine += 1
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
    with open("data/report.json", 'w') as f:
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
        
    with open("data/report.md", 'w') as f:
        f.write(md)
        
    print(md)
