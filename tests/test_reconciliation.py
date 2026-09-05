"""
Block 3 — Reconciliation engine: running unmatched pile, fuzzy bank match,
lifecycle sweep, and retroactive corrections.
"""
import os
import sys
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from api.main import app
from engine.reconcile import (
    apply_payment_event,
    get_ledger_row,
    ingest_bank_records,
    run_reconciliation_sweep,
    unmatched_pile_counts,
    upsert_payment,
)
from report.db import get_db

client = TestClient(app)


def _signup():
    email = f"recon_{uuid.uuid4().hex[:10]}@test.com"
    resp = client.post(
        "/api/signup",
        json={"email": email, "password": "password123", "merchant_name": "Recon Test"},
    )
    assert resp.status_code == 200
    data = resp.json()
    return data["merchant_id"], data["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_sweep_flags_old_authorized_payment():
    merchant_id, token = _signup()
    old = datetime.utcnow() - timedelta(hours=30)
    upsert_payment(
        merchant_id,
        "pay_stuck_auth",
        amount=100.0,
        status="AUTHORIZED",
        now=old,
    )
    # created_at/authorized_at were set to `old`; sweep at "now" should flag it
    result = run_reconciliation_sweep(merchant_id, now=datetime.utcnow())
    assert result["flagged"] >= 1

    res = client.get("/api/queue", headers=_auth(token))
    assert res.status_code == 200
    cats = [item.get("m2_category") for item in res.json()]
    assert "PARTIAL_MATCH_STUCK" in cats


def test_fuzzy_match_links_fee_adjusted_bank_row():
    merchant_id, _token = _signup()
    upsert_payment(merchant_id, "pay_fuzzy_1", amount=100.00, status="CAPTURED")
    result = ingest_bank_records(
        merchant_id,
        [{
            "external_id": "SETT-fuzzy-1",
            "txn_ref": "unrelated-utr",
            "amount": 98.50,
            "value_date": datetime.utcnow().strftime("%Y-%m-%d"),
            "fee_deducted": 1.50,
            "description": "NEFT in",
        }],
    )
    assert result["newly_matched"] == 1
    row = get_ledger_row(merchant_id, "pay_fuzzy_1")
    assert row["match_status"] == "MATCHED"


def test_second_batch_merges_into_unmatched_pile():
    merchant_id, token = _signup()
    upsert_payment(merchant_id, "pay_batch_a", amount=50.00, status="CAPTURED")
    upsert_payment(merchant_id, "pay_batch_b", amount=75.00, status="CAPTURED")

    ingest_bank_records(
        merchant_id,
        [{
            "external_id": "SETT-a",
            "txn_ref": "pay_batch_a",
            "amount": 50.00,
            "value_date": datetime.utcnow().strftime("%Y-%m-%d"),
            "fee_deducted": 0,
            "description": "batch 1",
        }],
    )
    pile_after_first = unmatched_pile_counts(merchant_id)
    assert get_ledger_row(merchant_id, "pay_batch_a")["match_status"] == "MATCHED"
    assert get_ledger_row(merchant_id, "pay_batch_b")["match_status"] == "UNMATCHED"
    assert pile_after_first["unmatched_payments"] == 1

    ingest_bank_records(
        merchant_id,
        [{
            "external_id": "SETT-b",
            "txn_ref": "pay_batch_b",
            "amount": 75.00,
            "value_date": datetime.utcnow().strftime("%Y-%m-%d"),
            "fee_deducted": 0,
            "description": "batch 2",
        }],
    )
    assert get_ledger_row(merchant_id, "pay_batch_a")["match_status"] == "MATCHED"
    assert get_ledger_row(merchant_id, "pay_batch_b")["match_status"] == "MATCHED"
    pile = unmatched_pile_counts(merchant_id)
    assert pile["unmatched_payments"] == 0
    assert pile["unmatched_bank"] == 0

    res = client.post("/api/reconcile", headers=_auth(token))
    assert res.status_code == 200
    body = res.json()
    assert "flagged" in body
    assert body["unmatched_payments"] == 0


def test_late_refund_reopens_matched_payment():
    merchant_id, token = _signup()
    upsert_payment(merchant_id, "pay_reopen", amount=200.00, status="CAPTURED")
    ingest_bank_records(
        merchant_id,
        [{
            "external_id": "SETT-reopen",
            "txn_ref": "pay_reopen",
            "amount": 200.00,
            "value_date": datetime.utcnow().strftime("%Y-%m-%d"),
            "fee_deducted": 0,
            "description": "settled",
        }],
    )
    assert get_ledger_row(merchant_id, "pay_reopen")["match_status"] == "MATCHED"

    apply_payment_event(
        merchant_id,
        event_type="refund.processed",
        payment_id="pay_reopen",
        amount=200.00,
    )
    row = get_ledger_row(merchant_id, "pay_reopen")
    assert row["match_status"] == "REOPENED"
    assert row["status"] == "REFUNDED"

    conn = get_db()
    corrections = conn.execute(
        "SELECT * FROM reconciliation_corrections WHERE merchant_id = ? AND payment_id = ?",
        (merchant_id, "pay_reopen"),
    ).fetchall()
    conn.close()
    assert len(corrections) == 1
    assert dict(corrections[0])["old_match_status"] == "MATCHED"
    assert dict(corrections[0])["new_match_status"] == "REOPENED"

    queue = client.get("/api/queue", headers=_auth(token)).json()
    assert any(item["m2_category"] == "RETROACTIVE_CORRECTION" for item in queue)


def test_bank_csv_upload_and_queue_age():
    merchant_id, token = _signup()
    upsert_payment(merchant_id, "pay_csv", amount=10.00, status="CAPTURED")
    today = datetime.utcnow().strftime("%Y-%m-%d")
    csv_body = f"settlement_id,txn_ref,settled_amount,settlement_date,fee_deducted\nSETT-csv,pay_csv,10.00,{today},0\n"
    res = client.post(
        "/api/bank-statement",
        headers=_auth(token),
        files={"file": ("stmt.csv", csv_body, "text/csv")},
    )
    assert res.status_code == 200
    assert res.json()["inserted"] == 1
    assert get_ledger_row(merchant_id, "pay_csv")["match_status"] == "MATCHED"

    conn = get_db()
    with conn:
        conn.execute(
            "INSERT INTO transactions (merchant_id, timestamp, txn_ref, source, m4_action) VALUES (?, ?, ?, 'RECONCILE', 'REVIEW')",
            (merchant_id, (datetime.utcnow() - timedelta(days=5)).isoformat(), "pay_old_open"),
        )
    conn.close()
    queue = client.get("/api/queue", headers=_auth(token)).json()
    aged = [item for item in queue if item["txn_ref"] == "pay_old_open"]
    assert aged
    assert aged[0]["days_unresolved"] >= 5
    assert aged[0]["priority"] is True

def test_human_agreement_on_dashboard():
    merchant_id, token = _signup()
    conn = get_db()
    with conn:
        conn.execute(
            "INSERT INTO transactions (merchant_id, timestamp, txn_ref, source, m4_action) VALUES (?, ?, 't1', 'BATCH', 'REVIEW')",
            (merchant_id, datetime.utcnow().isoformat()),
        )
        conn.execute(
            "INSERT INTO transactions (merchant_id, timestamp, txn_ref, source, m4_action) VALUES (?, ?, 't2', 'BATCH', 'REVIEW')",
            (merchant_id, datetime.utcnow().isoformat()),
        )
        conn.execute(
            "INSERT INTO decisions (merchant_id, timestamp, txn_ref, decision, reviewer_note) VALUES (?, ?, 't1', 'approve', '')",
            (merchant_id, datetime.utcnow().isoformat()),
        )
        conn.execute(
            "INSERT INTO decisions (merchant_id, timestamp, txn_ref, decision, reviewer_note) VALUES (?, ?, 't2', 'reject', '')",
            (merchant_id, datetime.utcnow().isoformat()),
        )
    conn.close()