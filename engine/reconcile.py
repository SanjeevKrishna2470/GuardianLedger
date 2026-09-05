"""
Running unmatched pile: payments_ledger holds current payment state;
bank_statement_lines holds unmatched (and matched) bank records.
Each new record is checked against the existing unmatched pile — we never
restart reconciliation from a fresh batch.

TODO: scheduled bank-statement ingestion (SFTP/email pull). Until that exists,
merchants upload a CSV via POST /api/bank-statement (the load-bearing path).
"""
import csv
import io
import uuid
from datetime import datetime, timedelta

from engine.trust_boundary import Action
from report.audit_log import logger
from report.db import get_db

AMOUNT_TOLERANCE = 2.00  # rupees
DATE_SKEW_DAYS = 2
AUTH_STUCK_HOURS = 24
SETTLEMENT_DELAY_DAYS = 3
ESCALATION_DAYS = 3

STATUS_FROM_EVENT = {
    "payment.authorized": "AUTHORIZED",
    "payment.captured": "CAPTURED",
    "payment.failed": "FAILED",
    "refund.processed": "REFUNDED",
    "settlement.processed": "SETTLED",
}

CONTRADICTING_AFTER_MATCHED = {"FAILED", "REFUNDED"}


def _now(now=None) -> datetime:
    return now or datetime.utcnow()


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _parse_dt(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).replace("Z", "")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:26] if "T" in text else text[:10], fmt if "T" in text else "%Y-%m-%d")
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def parse_bank_csv(text: str) -> list:
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for raw in reader:
        row = { (k or "").strip().lower(): (v.strip() if isinstance(v, str) else v) for k, v in raw.items() }
        amount_raw = row.get("settled_amount") or row.get("amount") or "0"
        fee_raw = row.get("fee_deducted") or "0"
        try:
            amount = float(amount_raw)
        except (TypeError, ValueError):
            amount = 0.0
        try:
            fee = float(fee_raw)
        except (TypeError, ValueError):
            fee = 0.0
        external_id = row.get("settlement_id") or row.get("external_id") or ""
        txn_ref = row.get("txn_ref") or row.get("utr") or row.get("payment_id") or ""
        if not external_id:
            external_id = f"gen_{uuid.uuid4().hex[:16]}"
        rows.append({
            "external_id": external_id,
            "txn_ref": txn_ref,
            "amount": amount,
            "value_date": row.get("settlement_date") or row.get("date") or row.get("value_date") or "",
            "fee_deducted": fee,
            "description": row.get("description") or "",
        })
    return rows


def get_ledger_row(merchant_id: str, payment_id: str):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM payments_ledger WHERE merchant_id = ? AND payment_id = ?",
        (merchant_id, payment_id),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def upsert_payment(
    merchant_id: str,
    payment_id: str,
    *,
    order_id=None,
    amount=None,
    currency="INR",
    status="AUTHORIZED",
    event_type=None,
    now=None,
):
    """Insert or update current payment state. Does not wipe match_status on routine updates."""
    now_dt = _now(now)
    stamp = _iso(now_dt)
    existing = get_ledger_row(merchant_id, payment_id)

    authorized_at = existing["authorized_at"] if existing else None
    captured_at = existing["captured_at"] if existing else None
    settled_at = existing["settled_at"] if existing else None
    if status == "AUTHORIZED" and not authorized_at:
        authorized_at = stamp
    if status == "CAPTURED" and not captured_at:
        captured_at = stamp
    if status == "SETTLED" and not settled_at:
        settled_at = stamp

    conn = get_db()
    if existing:
        with conn:
            conn.execute(
                """
                UPDATE payments_ledger
                   SET order_id = COALESCE(?, order_id),
                       amount = COALESCE(?, amount),
                       currency = COALESCE(?, currency),
                       status = ?,
                       authorized_at = ?,
                       captured_at = ?,
                       settled_at = ?,
                       updated_at = ?
                 WHERE merchant_id = ? AND payment_id = ?
                """,
                (
                    order_id,
                    amount,
                    currency,
                    status,
                    authorized_at,
                    captured_at,
                    settled_at,
                    stamp,
                    merchant_id,
                    payment_id,
                ),
            )
    else:
        with conn:
            conn.execute(
                """
                INSERT INTO payments_ledger (
                    merchant_id, payment_id, order_id, amount, currency, status,
                    match_status, exception_flag, priority, unmatched_since,
                    authorized_at, captured_at, settled_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'UNMATCHED', NULL, 0, ?, ?, ?, ?, ?, ?)
                """,
                (
                    merchant_id, payment_id, order_id, amount, currency, status,
                    stamp, authorized_at, captured_at, settled_at, stamp, stamp,
                ),
            )
    conn.close()
    return get_ledger_row(merchant_id, payment_id)


def log_correction(
    merchant_id: str,
    payment_id: str,
    *,
    old_status,
    new_status,
    old_match_status,
    new_match_status,
    old_amount=None,
    new_amount=None,
    reason="",
    now=None,
):
    conn = get_db()
    with conn:
        conn.execute(
            """
            INSERT INTO reconciliation_corrections
                (merchant_id, payment_id, old_status, new_status,
                 old_match_status, new_match_status, old_amount, new_amount, reason, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                merchant_id, payment_id, old_status, new_status,
                old_match_status, new_match_status, old_amount, new_amount,
                reason, _iso(_now(now)),
            ),
        )
    conn.close()


def reopen_payment(merchant_id: str, payment_id: str, reason: str, new_status=None, new_amount=None, now=None):
    """Late-arriving contradiction: reopen for review and keep old + new state in the correction log."""
    existing = get_ledger_row(merchant_id, payment_id)
    if not existing:
        return None
    new_status = new_status or existing["status"]
    log_correction(
        merchant_id,
        payment_id,
        old_status=existing["status"],
        new_status=new_status,
        old_match_status=existing["match_status"],
        new_match_status="REOPENED",
        old_amount=existing.get("amount"),
        new_amount=new_amount if new_amount is not None else existing.get("amount"),
        reason=reason,
        now=now,
    )
    stamp = _iso(_now(now))
    conn = get_db()
    with conn:
        conn.execute(
            """
            UPDATE payments_ledger
               SET status = ?,
                   match_status = 'REOPENED',
                   amount = COALESCE(?, amount),
                   unmatched_since = ?,
                   priority = 1,
                   updated_at = ?
             WHERE merchant_id = ? AND payment_id = ?
            """,
            (new_status, new_amount, stamp, stamp, merchant_id, payment_id),
        )
    conn.close()

    logger.log_transaction(
        merchant_id=merchant_id,
        txn_ref=payment_id,
        match_result="REOPENED",
        category="RETROACTIVE_CORRECTION",
        extracted_data={
            "old_status": existing["status"],
            "new_status": new_status,
            "old_match_status": existing["match_status"],
            "old_amount": existing.get("amount"),
            "new_amount": new_amount,
        },
        action=Action.REVIEW,
        reason=reason,
        source="RECONCILE",
        raw_evidence={
            "old_state": dict(existing),
            "new_state": {"status": new_status, "amount": new_amount, "match_status": "REOPENED"},
            "reason": reason,
        },
    )
    return get_ledger_row(merchant_id, payment_id)


def apply_payment_event(
    merchant_id: str,
    *,
    event_type: str,
    payment_id: str,
    order_id=None,
    amount=None,
    currency="INR",
    now=None,
):
    """
    Apply a gateway event to the running ledger, then incrementally match
    against the unmatched bank pile. Contradictions reopen matched items.
    """
    status = STATUS_FROM_EVENT.get(event_type, "AUTHORIZED")
    existing = get_ledger_row(merchant_id, payment_id)

    if existing and existing.get("match_status") == "MATCHED":
        amount_delta = None
        if amount is not None and existing.get("amount") is not None:
            amount_delta = abs(float(amount) - float(existing["amount"]))
        contradicts_status = status in CONTRADICTING_AFTER_MATCHED
        contradicts_amount = amount_delta is not None and amount_delta > AMOUNT_TOLERANCE and event_type != "refund.processed"
        if contradicts_status or contradicts_amount:
            reason = (
                f"Late {event_type} contradicts previously MATCHED payment "
                f"(was {existing['status']}/{existing['match_status']})"
            )
            reopen_payment(
                merchant_id, payment_id, reason,
                new_status=status, new_amount=amount, now=now,
            )
            try_match_unmatched_pile(merchant_id)
            return get_ledger_row(merchant_id, payment_id)

    row = upsert_payment(
        merchant_id,
        payment_id,
        order_id=order_id,
        amount=amount,
        currency=currency,
        status=status,
        event_type=event_type,
        now=now,
    )
    try_match_unmatched_pile(merchant_id)
    return row


def ingest_bank_records(merchant_id: str, records: list, now=None) -> dict:
    """Append new bank lines to the unmatched pile (skip duplicates) and rematch incrementally."""
    inserted = 0
    skipped = 0
    stamp = _iso(_now(now))
    conn = get_db()
    for rec in records:
        existing = conn.execute(
            "SELECT 1 FROM bank_statement_lines WHERE merchant_id = ? AND external_id = ?",
            (merchant_id, rec["external_id"]),
        ).fetchone()
        if existing:
            skipped += 1
            continue
        with conn:
            conn.execute(
                """
                INSERT INTO bank_statement_lines
                    (merchant_id, external_id, txn_ref, amount, value_date,
                     fee_deducted, description, match_status, matched_payment_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'UNMATCHED', NULL, ?)
                """,
                (
                    merchant_id,
                    rec.get("external_id"),
                    rec.get("txn_ref") or None,
                    rec.get("amount"),
                    rec.get("value_date") or None,
                    rec.get("fee_deducted") or 0,
                    rec.get("description") or None,
                    stamp,
                ),
            )
        inserted += 1
    conn.close()
    matched = try_match_unmatched_pile(merchant_id)
    return {"inserted": inserted, "skipped_duplicates": skipped, "newly_matched": matched}


def _unmatched_payments(conn, merchant_id):
    rows = conn.execute(
        """
        SELECT * FROM payments_ledger
         WHERE merchant_id = ?
           AND match_status IN ('UNMATCHED', 'REOPENED', 'PARTIAL')
           AND status IN ('AUTHORIZED', 'CAPTURED', 'SETTLED')
        """,
        (merchant_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _unmatched_bank(conn, merchant_id):
    rows = conn.execute(
        """
        SELECT * FROM bank_statement_lines
         WHERE merchant_id = ? AND match_status = 'UNMATCHED'
        """,
        (merchant_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _mark_matched(conn, merchant_id, payment_id, bank_id, now):
    stamp = _iso(_now(now))
    conn.execute(
        """
        UPDATE payments_ledger
           SET match_status = 'MATCHED', exception_flag = NULL, priority = 0, updated_at = ?
         WHERE merchant_id = ? AND payment_id = ?
        """,
        (stamp, merchant_id, payment_id),
    )
    conn.execute(
        """
        UPDATE bank_statement_lines
           SET match_status = 'MATCHED', matched_payment_id = ?
         WHERE id = ? AND merchant_id = ?
        """,
        (payment_id, bank_id, merchant_id),
    )


def _within_date_window(payment, bank_row) -> bool:
    bank_dt = _parse_dt(bank_row.get("value_date"))
    if not bank_dt:
        return True
    candidates = [
        _parse_dt(payment.get("captured_at")),
        _parse_dt(payment.get("authorized_at")),
        _parse_dt(payment.get("created_at")),
        _parse_dt(payment.get("updated_at")),
    ]
    pay_dt = next((d for d in candidates if d), None)
    if not pay_dt:
        return True
    return abs((pay_dt.date() - bank_dt.date()).days) <= DATE_SKEW_DAYS


def _amount_close(payment, bank_row) -> bool:
    pay_amt = float(payment.get("amount") or 0)
    bank_amt = float(bank_row.get("amount") or 0)
    fee = float(bank_row.get("fee_deducted") or 0)
    # Net settlement vs gross capture, plus a flat rupee tolerance for fees/rounding.
    return (
        abs(pay_amt - bank_amt) <= AMOUNT_TOLERANCE
        or abs(pay_amt - (bank_amt + fee)) <= AMOUNT_TOLERANCE
    )


def fuzzy_match_candidates(payment, bank_rows) -> list:
    """Rank unmatched bank rows that fall inside the amount/date window."""
    scored = []
    for bank in bank_rows:
        txn_hit = bool(bank.get("txn_ref") and bank["txn_ref"] == payment["payment_id"])
        if not txn_hit and not (_amount_close(payment, bank) and _within_date_window(payment, bank)):
            continue
        pay_amt = float(payment.get("amount") or 0)
        bank_amt = float(bank.get("amount") or 0)
        fee = float(bank.get("fee_deducted") or 0)
        delta = min(abs(pay_amt - bank_amt), abs(pay_amt - (bank_amt + fee)))
        score = (0 if txn_hit else 1, delta)
        scored.append((score, bank))
    scored.sort(key=lambda x: x[0])
    return [b for _, b in scored]


def try_match_unmatched_pile(merchant_id: str, now=None) -> int:
    """Match currently unmatched payments against currently unmatched bank lines only."""
    conn = get_db()
    payments = _unmatched_payments(conn, merchant_id)
    bank_rows = _unmatched_bank(conn, merchant_id)
    used_bank_ids = set()
    matched = 0
    for payment in payments:
        available = [b for b in bank_rows if b["id"] not in used_bank_ids]
        candidates = fuzzy_match_candidates(payment, available)
        if not candidates:
            continue
        bank = candidates[0]
        with conn:
            _mark_matched(conn, merchant_id, payment["payment_id"], bank["id"], now)
        used_bank_ids.add(bank["id"])
        matched += 1
        logger.log_transaction(
            merchant_id=merchant_id,
            txn_ref=payment["payment_id"],
            match_result="MATCHED",
            category="Settlement",
            extracted_data={
                "bank_external_id": bank.get("external_id"),
                "bank_amount": bank.get("amount"),
                "ledger_amount": payment.get("amount"),
            },
            action=Action.MATCH,
            reason="Incremental fuzzy match against unmatched bank pile",
            source="RECONCILE",
            raw_evidence={"gateway_record": payment, "bank_record": bank},
        )
    conn.close()
    return matched


def fuzzy_match_bank_statement(merchant_id: str, records: list, now=None) -> dict:
    """Ingest a raw CSV/JSON array of bank records and fuzzy-match the unmatched pile."""
    return ingest_bank_records(merchant_id, records, now=now)


def _already_flagged(merchant_id: str, payment_id: str, category: str) -> bool:
    conn = get_db()
    row = conn.execute(
        """
        SELECT 1 FROM transactions
         WHERE merchant_id = ? AND txn_ref = ? AND m2_category = ?
         LIMIT 1
        """,
        (merchant_id, payment_id, category),
    ).fetchone()
    conn.close()
    return row is not None


def _set_exception_flag(merchant_id: str, payment_id: str, flag: str, priority: int, now=None):
    stamp = _iso(_now(now))
    conn = get_db()
    with conn:
        conn.execute(
            """
            UPDATE payments_ledger
               SET exception_flag = ?, priority = ?, updated_at = ?
             WHERE merchant_id = ? AND payment_id = ?
            """,
            (flag, priority, stamp, merchant_id, payment_id),
        )
    conn.close()


def escalate_unresolved(merchant_id: str, now=None) -> int:
    """Unresolved > 3 days gets a priority flag on the ledger and any open queue rows."""
    now_dt = _now(now)
    cutoff = now_dt - timedelta(days=ESCALATION_DAYS)
    conn = get_db()
    rows = conn.execute(
        """
        SELECT * FROM payments_ledger
         WHERE merchant_id = ? AND match_status IN ('UNMATCHED', 'REOPENED', 'PARTIAL')
        """,
        (merchant_id,),
    ).fetchall()
    escalated = 0
    for row in rows:
        payment = dict(row)
        since = _parse_dt(payment.get("unmatched_since") or payment.get("created_at"))
        if since and since <= cutoff and not payment.get("priority"):
            with conn:
                conn.execute(
                    "UPDATE payments_ledger SET priority = 1, updated_at = ? WHERE merchant_id = ? AND payment_id = ?",
                    (_iso(now_dt), merchant_id, payment["payment_id"]),
                )
            escalated += 1
    open_rows = conn.execute(
        """
        SELECT id, timestamp, priority FROM transactions
         WHERE merchant_id = ? AND m4_action IN ('REVIEW', 'EXCEPTION', 'QUARANTINE')
        """,
        (merchant_id,),
    ).fetchall()
    for row in open_rows:
        item = dict(row)
        ts = _parse_dt(item.get("timestamp"))
        if ts and (now_dt - ts).days > ESCALATION_DAYS:
            with conn:
                conn.execute("UPDATE transactions SET priority = 1 WHERE id = ?", (item["id"],))
    conn.close()
    return escalated


def run_reconciliation_sweep(merchant_id: str, now=None) -> dict:
    """
    Sweep the running unmatched pile:
    - AUTHORIZED not CAPTURED after 24h -> PARTIAL_MATCH_STUCK
    - CAPTURED not SETTLED after 3 days -> SETTLEMENT_DELAYED
    - unresolved > 3 days -> priority
    """
    now_dt = _now(now)
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM payments_ledger WHERE merchant_id = ?",
        (merchant_id,),
    ).fetchall()
    conn.close()

    flagged = 0
    for raw in rows:
        payment = dict(raw)
        payment_id = payment["payment_id"]
        status = payment["status"]

        if status == "AUTHORIZED":
            start = _parse_dt(payment.get("authorized_at") or payment.get("created_at"))
            if start and now_dt - start >= timedelta(hours=AUTH_STUCK_HOURS):
                category = "PARTIAL_MATCH_STUCK"
                if not _already_flagged(merchant_id, payment_id, category):
                    _set_exception_flag(merchant_id, payment_id, category, 1, now=now_dt)
                    logger.log_transaction(
                        merchant_id=merchant_id,
                        txn_ref=payment_id,
                        match_result="UNMATCHED",
                        category=category,
                        extracted_data={"status": status, "authorized_at": payment.get("authorized_at")},
                        action=Action.REVIEW,
                        reason="Authorized but not captured after 24 hours",
                        source="RECONCILE",
                        raw_evidence={"ledger_record": payment},
                    )
                    flagged += 1

        if status == "CAPTURED":
            start = _parse_dt(payment.get("captured_at") or payment.get("created_at"))
            if start and now_dt - start >= timedelta(days=SETTLEMENT_DELAY_DAYS):
                category = "SETTLEMENT_DELAYED"
                if not _already_flagged(merchant_id, payment_id, category):
                    _set_exception_flag(merchant_id, payment_id, category, 1, now=now_dt)
                    logger.log_transaction(
                        merchant_id=merchant_id,
                        txn_ref=payment_id,
                        match_result="UNMATCHED",
                        category=category,
                        extracted_data={"status": status, "captured_at": payment.get("captured_at")},
                        action=Action.EXCEPTION,
                        reason="Captured but not settled after 3 days",
                        source="RECONCILE",
                        raw_evidence={"ledger_record": payment},
                    )
                    flagged += 1

    escalate_unresolved(merchant_id, now=now_dt)
    newly_matched = try_match_unmatched_pile(merchant_id, now=now_dt)
    return {"flagged": flagged, "newly_matched": newly_matched}


def unmatched_pile_counts(merchant_id: str) -> dict:
    conn = get_db()
    pay = conn.execute(
        "SELECT COUNT(*) AS n FROM payments_ledger WHERE merchant_id = ? AND match_status IN ('UNMATCHED', 'REOPENED', 'PARTIAL')",
        (merchant_id,),
    ).fetchone()
    bank = conn.execute(
        "SELECT COUNT(*) AS n FROM bank_statement_lines WHERE merchant_id = ? AND match_status = 'UNMATCHED'",
        (merchant_id,),
    ).fetchone()
    conn.close()
    return {
        "unmatched_payments": int(pay["n"] if pay else 0),
        "unmatched_bank": int(bank["n"] if bank else 0),
    }


def list_ledger(merchant_id: str) -> list:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM payments_ledger WHERE merchant_id = ? ORDER BY updated_at DESC",
        (merchant_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def human_agreement_stats(merchant_id: str, last_n: int = 100) -> dict:
    """
    Accuracy going forward: share of human reviewer decisions that agree
    (approve) vs disagree (reject) with AI-assisted / engine-proposed items.
    Replaces compare-against-answer-key measurement.
    """
    conn = get_db()
    rows = conn.execute(
        """
        SELECT d.decision
          FROM decisions d
         WHERE d.merchant_id = ?
         ORDER BY d.id DESC
         LIMIT ?
        """,
        (merchant_id, last_n),
    ).fetchall()
    conn.close()
    decisions = [dict(r)["decision"] for r in rows]
    if not decisions:
        return {
            "human_agreement_rate": None,
            "human_decision_count": 0,
            "agreements": 0,
            "disagreements": 0,
        }
    agreements = sum(1 for d in decisions if str(d).lower() in ("approve", "approved", "agree"))
    disagreements = sum(1 for d in decisions if str(d).lower() in ("reject", "rejected", "disagree"))
    counted = agreements + disagreements
    rate = round((agreements / counted) * 100, 2) if counted else None
    return {
        "human_agreement_rate": rate,
        "human_decision_count": len(decisions),
        "agreements": agreements,
        "disagreements": disagreements,
    }


def days_unresolved_for(timestamp, now=None) -> int:
    ts = _parse_dt(timestamp)
    if not ts:
        return 0
    delta = _now(now) - ts
    return max(0, delta.days)
