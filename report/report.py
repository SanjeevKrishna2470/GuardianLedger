import json
import os
import time

from engine.reconcile import human_agreement_stats, unmatched_pile_counts
from report.db import get_db, _PROJECT_ROOT

def generate_report(merchant_id: str, start_time=None, end_time=None):
    conn = get_db()
    rows = conn.execute("SELECT m4_action, m2_category FROM transactions WHERE merchant_id = ?", (merchant_id,)).fetchall()

    # Join decisions back to the m4_action they reviewed, so we can tell
    # agreement-with-AI apart from a raw approve/reject ratio, and compute
    # a real false-quarantine rate instead of a hardcoded zero.
    joined = conn.execute(
        """
        SELECT d.decision, t.m4_action
          FROM decisions d
          JOIN transactions t
            ON t.merchant_id = d.merchant_id AND t.txn_ref = d.txn_ref
         WHERE d.merchant_id = ?
        """,
        (merchant_id,),
    ).fetchall()
    conn.close()

    total = len(rows)
    matched = 0
    exceptions = {}
    quarantined = 0

    for row in rows:
        action = row["m4_action"]
        cat = row["m2_category"]
        if action == "MATCH" or action == "POST":
            matched += 1
        elif action == "QUARANTINE":
            quarantined += 1
        elif action == "EXCEPTION" or cat:
            if cat:
                exceptions[cat] = exceptions.get(cat, 0) + 1

    # A false quarantine = human reviewed a QUARANTINE item and approved it
    # (i.e. it wasn't actually adversarial/invalid).
    reviewed_quarantines = [j for j in joined if j["m4_action"] == "QUARANTINE"]
    false_quarantine = sum(
        1 for j in reviewed_quarantines
        if str(j["decision"]).lower() in ("approve", "approved", "agree")
    )
    reviewed_quarantine_count = len(reviewed_quarantines)

    throughput = 0
    if start_time and end_time:
        duration = end_time - start_time
        throughput = total / duration if duration > 0 else total

    agreement = human_agreement_stats(merchant_id)
    pile = unmatched_pile_counts(merchant_id)

    report_data = {
        "total_processed": total,
        "match_rate": round((matched / total * 100), 2) if total > 0 else 0,
        "quarantine_count": quarantined,
        "false_quarantine_rate": (
            round((false_quarantine / reviewed_quarantine_count * 100), 2)
            if reviewed_quarantine_count > 0 else None
        ),
        "reviewed_quarantine_count": reviewed_quarantine_count,
        "throughput_records_per_sec": round(throughput, 2),
        "exception_breakdown": exceptions,
        "human_agreement_rate": agreement["human_agreement_rate"],
        "human_decision_count": agreement["human_decision_count"],
        "human_agreements": agreement["agreements"],
        "human_disagreements": agreement["disagreements"],
        "unmatched_payments": pile["unmatched_payments"],
        "unmatched_bank": pile["unmatched_bank"],
    }

    return report_data
