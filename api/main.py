import json
import os
import uuid
import datetime
import sys

from api.rate_limit import is_rate_limited

WEBHOOK_MAX_ATTEMPTS = 30
WEBHOOK_WINDOW_SECONDS = 60

from fastapi import FastAPI, Request, HTTPException, Header, Depends, BackgroundTasks, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import razorpay

# Ensure project root is on path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.trust_boundary import Action
from engine.reconcile import (
    apply_payment_event,
    days_unresolved_for,
    ingest_bank_records,
    list_ledger,
    parse_bank_csv,
    run_reconciliation_sweep,
    unmatched_pile_counts,
)
from report.audit_log import logger
from report.report import generate_report
from report.db import get_db, _PROJECT_ROOT
from api.auth import router as auth_router, get_current_user
from api.crypto import encrypt_value, decrypt_value

app = FastAPI(title="Guardian Ledger API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)

def _row_to_dict(row) -> dict:
    d = dict(row)
    for field in ("m3_extracted", "raw_evidence"):
        if d.get(field) and isinstance(d[field], str):
            try:
                d[field] = json.loads(d[field])
            except Exception:
                pass
    return d


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class ActionRequest(BaseModel):
    txn_ref: str
    decision: str  # "approve" or "reject"
    reviewer_note: str = ""

class OrderRequest(BaseModel):
    amount: int
    currency: str = "INR"

class VerifyPaymentRequest(BaseModel):
    payment_id: str
    order_id: str
    signature: str

class MerchantKeysUpdate(BaseModel):
    key_id: str
    key_secret: str
    webhook_secret: str

MAX_BANK_CSV_BYTES = 2 * 1024 * 1024


def _annotate_queue_item(row: dict) -> dict:
    days = days_unresolved_for(row.get("timestamp"))
    row["days_unresolved"] = days
    row["priority"] = bool(row.get("priority")) or days > 3
    return row


# ---------------------------------------------------------------------------
# Pipeline / dashboard
# ---------------------------------------------------------------------------

@app.post("/api/run-pipeline")
def run_pipeline_endpoint(current_user: dict = Depends(get_current_user)):
    try:
        report_data = generate_report(current_user["merchant_id"])
        return report_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/dashboard")
def get_dashboard(current_user: dict = Depends(get_current_user)):
    return generate_report(current_user["merchant_id"])


# ---------------------------------------------------------------------------
# Transactions & queue
# ---------------------------------------------------------------------------

@app.get("/api/queue")
def get_review_queue(current_user: dict = Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM transactions WHERE merchant_id = ? AND m4_action IN ('REVIEW','EXCEPTION','QUARANTINE') ORDER BY id DESC",
        (current_user["merchant_id"],)
    ).fetchall()
    conn.close()
    items = [_annotate_queue_item(_row_to_dict(r)) for r in rows]
    items.sort(key=lambda x: (not x.get("priority"), -(x.get("days_unresolved") or 0)))
    return items

@app.get("/api/transactions")
def get_all_transactions(current_user: dict = Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute("SELECT * FROM transactions WHERE merchant_id = ? ORDER BY id DESC", (current_user["merchant_id"],)).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Reviewer action
# ---------------------------------------------------------------------------

@app.post("/api/action")
def post_action(req: ActionRequest, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    with conn:
        conn.execute(
            "INSERT INTO decisions (merchant_id, timestamp, txn_ref, decision, reviewer_note) VALUES (?, ?, ?, ?, ?)",
            (current_user["merchant_id"], datetime.datetime.utcnow().isoformat(), req.txn_ref, req.decision, req.reviewer_note),
        )
    conn.close()
    return {"status": "ok", "decision": req.decision, "txn_ref": req.txn_ref}


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------

@app.post("/api/reconcile")
def post_reconcile(current_user: dict = Depends(get_current_user)):
    merchant_id = current_user["merchant_id"]
    result = run_reconciliation_sweep(merchant_id)
    result.update(unmatched_pile_counts(merchant_id))
    return result


@app.get("/api/ledger")
def get_payments_ledger(current_user: dict = Depends(get_current_user)):
    return list_ledger(current_user["merchant_id"])


@app.post("/api/bank-statement")
async def upload_bank_statement(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    raw = await file.read()
    if len(raw) > MAX_BANK_CSV_BYTES:
        raise HTTPException(status_code=413, detail="Bank statement file is too large (max 2MB).")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Bank statement must be UTF-8 CSV.")
    records = parse_bank_csv(text)
    if not records:
        raise HTTPException(status_code=400, detail="No bank statement rows found.")
    result = ingest_bank_records(current_user["merchant_id"], records)
    result.update(unmatched_pile_counts(current_user["merchant_id"]))
    return result


# ---------------------------------------------------------------------------
# Merchant Keys
# ---------------------------------------------------------------------------

@app.post("/api/merchant/keys")
def update_merchant_keys(req: MerchantKeysUpdate, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    with conn:
        conn.execute(
            """
            UPDATE merchants 
            SET razorpay_key_id_enc = ?, 
                razorpay_key_secret_enc = ?, 
                razorpay_webhook_secret_enc = ?
            WHERE id = ?
            """,
            (
                encrypt_value(req.key_id),
                encrypt_value(req.key_secret),
                encrypt_value(req.webhook_secret),
                current_user["merchant_id"]
            )
        )
    conn.close()
    return {"status": "ok"}

@app.get("/api/merchant/keys")
def get_merchant_keys_status(current_user: dict = Depends(get_current_user)):
    conn = get_db()
    row = conn.execute("SELECT razorpay_key_id_enc, razorpay_webhook_secret_enc FROM merchants WHERE id = ?", (current_user["merchant_id"],)).fetchone()
    conn.close()
    if not row:
        return {"has_keys": False}
    
    return {
        "has_keys": bool(row["razorpay_key_id_enc"] and row["razorpay_webhook_secret_enc"]),
        "key_id_preview": decrypt_value(row["razorpay_key_id_enc"])[:8] + "..." if row["razorpay_key_id_enc"] else None
    }


# ---------------------------------------------------------------------------
# Razorpay integration
# ---------------------------------------------------------------------------

def get_razorpay_client_for_merchant(merchant_id: str):
    conn = get_db()
    row = conn.execute("SELECT razorpay_key_id_enc, razorpay_key_secret_enc FROM merchants WHERE id = ?", (merchant_id,)).fetchone()
    conn.close()
    
    if not row or not row["razorpay_key_id_enc"] or not row["razorpay_key_secret_enc"]:
        raise HTTPException(status_code=400, detail="Razorpay credentials not configured for this merchant.")
        
    key_id = decrypt_value(row["razorpay_key_id_enc"])
    key_secret = decrypt_value(row["razorpay_key_secret_enc"])
    
    return razorpay.Client(auth=(key_id, key_secret)), key_id

@app.post("/api/orders")
def create_order(req: OrderRequest, current_user: dict = Depends(get_current_user)):
    client, key_id = get_razorpay_client_for_merchant(current_user["merchant_id"])
    data = {
        "amount": req.amount,
        "currency": req.currency,
        "receipt": f"receipt_{uuid.uuid4().hex[:8]}",
        "payment_capture": 1,
    }
    try:
        order = client.order.create(data=data)
        return {
            "order_id": order["id"],
            "amount": order["amount"],
            "currency": order["currency"],
            "key_id": key_id,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/verify-payment")
def verify_payment(req: VerifyPaymentRequest, current_user: dict = Depends(get_current_user)):
    merchant_id = current_user["merchant_id"]
    client, _ = get_razorpay_client_for_merchant(merchant_id)
    try:
        client.utility.verify_payment_signature({
            "razorpay_order_id": req.order_id,
            "razorpay_payment_id": req.payment_id,
            "razorpay_signature": req.signature,
        })
    except Exception as e:
        logger.log_transaction(
            merchant_id=merchant_id,
            txn_ref=req.payment_id,
            match_result="FAILED",
            category="SECURITY_EXCEPTION",
            extracted_data={"order_id": req.order_id, "error": str(e)},
            action=Action.QUARANTINE,
            reason="Checkout payment signature verification failed",
            source="LIVE_CHECKOUT",
            raw_evidence={"error": str(e), "order_id": req.order_id, "signature": req.signature},
        )
        raise HTTPException(status_code=400, detail="Invalid payment signature")

    if not logger.is_logged(merchant_id, req.payment_id):
        logger.log_transaction(
            merchant_id=merchant_id,
            txn_ref=req.payment_id,
            match_result="MATCHED",
            category="Settlement",
            extracted_data={"event": "payment.verified", "order_id": req.order_id},
            action=Action.MATCH,
            reason="Live checkout payment verified successfully",
            source="LIVE_CHECKOUT",
            raw_evidence={
                "gateway_record": {
                    "id": req.payment_id,
                    "order_id": req.order_id,
                    "signature": req.signature,
                    "status": "captured",
                },
                "event": "payment.verified",
            },
        )
    return {"status": "ok", "message": "Payment verified and recorded", "txn_ref": req.payment_id}

def process_webhook_event(merchant_id: str, payload: dict):
    event_type = payload.get("event")

    if event_type in ("payment.captured", "payment.authorized"):
        payment_entity = payload["payload"]["payment"]["entity"]
        txn_ref = payment_entity["id"]
        apply_payment_event(
            merchant_id,
            event_type=event_type,
            payment_id=txn_ref,
            order_id=payment_entity.get("order_id"),
            amount=(payment_entity.get("amount") or 0) / 100,
            currency=payment_entity.get("currency") or "INR",
        )
        if not logger.is_logged(merchant_id, txn_ref):
            logger.log_transaction(
                merchant_id=merchant_id,
                txn_ref=txn_ref,
                match_result="UNMATCHED",
                category="Settlement",
                extracted_data={"event": event_type, "amount": payment_entity.get("amount", 0) / 100},
                action="RECORDED",
                reason=f"Razorpay {event_type} recorded on the unmatched pile",
                source="LIVE_WEBHOOK",
                raw_evidence={
                    "gateway_record": payment_entity,
                    "event": event_type,
                    "order_id": payment_entity.get("order_id"),
                },
            )

    elif event_type == "payment.failed":
        payment_entity = payload["payload"]["payment"]["entity"]
        txn_ref = payment_entity["id"]
        apply_payment_event(
            merchant_id,
            event_type=event_type,
            payment_id=txn_ref,
            order_id=payment_entity.get("order_id"),
            amount=(payment_entity.get("amount") or 0) / 100,
            currency=payment_entity.get("currency") or "INR",
        )
        logger.log_transaction(
            merchant_id=merchant_id,
            txn_ref=txn_ref,
            match_result="FAILED",
            category="PAYMENT_FAILED",
            extracted_data={"event": event_type, "error_description": payment_entity.get("error_description")},
            action=Action.EXCEPTION,
            reason=f"Razorpay payment failed via live webhook: {payment_entity.get('error_description', 'unknown')}",
            source="LIVE_WEBHOOK",
            raw_evidence={"gateway_record": payment_entity, "event": event_type},
        )

    elif event_type == "refund.processed":
        refund_entity = payload["payload"]["refund"]["entity"]
        txn_ref = refund_entity["payment_id"]
        apply_payment_event(
            merchant_id,
            event_type=event_type,
            payment_id=txn_ref,
            amount=(refund_entity.get("amount") or 0) / 100,
        )
        logger.log_transaction(
            merchant_id=merchant_id,
            txn_ref=txn_ref,
            match_result="NEEDS_CLASSIFICATION",
            category="REFUND",
            extracted_data={
                "event": "refund.processed",
                "refund_id": refund_entity.get("id"),
                "amount": refund_entity.get("amount", 0) / 100,
            },
            action=Action.REVIEW,
            reason="Refund processed by Razorpay via live webhook",
            source="LIVE_WEBHOOK",
            raw_evidence={
                "gateway_record": refund_entity,
                "event": "refund.processed",
                "payment_id": refund_entity.get("payment_id"),
            },
        )

    elif event_type == "settlement.processed":
        entity = (payload.get("payload") or {}).get("settlement", {}).get("entity") or {}
        payment_ids = list(entity.get("payment_ids") or [])
        if entity.get("payment_id"):
            payment_ids.append(entity["payment_id"])
        amount = (entity.get("amount") or 0) / 100 if entity.get("amount") else None
        for txn_ref in payment_ids:
            apply_payment_event(
                merchant_id,
                event_type=event_type,
                payment_id=txn_ref,
                amount=amount,
            )


@app.post("/api/webhooks/razorpay/{merchant_id}")
async def razorpay_webhook(merchant_id: str, request: Request, background_tasks: BackgroundTasks, x_razorpay_signature: str = Header(None)):
    if is_rate_limited(f"webhook:{merchant_id}", WEBHOOK_MAX_ATTEMPTS, WEBHOOK_WINDOW_SECONDS):
        raise HTTPException(status_code=429, detail="Too many webhook requests for this merchant.")
    raw_body = await request.body()
    
    conn = get_db()
    row = conn.execute("SELECT razorpay_webhook_secret_enc FROM merchants WHERE id = ?", (merchant_id,)).fetchone()
    
    if not row or not row["razorpay_webhook_secret_enc"]:
        conn.close()
        raise HTTPException(status_code=500, detail="Webhook secret not configured for this merchant.")
        
    webhook_secret = decrypt_value(row["razorpay_webhook_secret_enc"])

    if not x_razorpay_signature:
        conn.close()
        raise HTTPException(status_code=400, detail="Missing signature")

    client = razorpay.Client(auth=("mock", "mock")) 
    
    try:
        client.utility.verify_webhook_signature(
            raw_body.decode("utf-8"), x_razorpay_signature, webhook_secret
        )
    except Exception as e:
        conn.close()
        logger.log_transaction(
            merchant_id=merchant_id,
            txn_ref="UNKNOWN",
            match_result="FAILED",
            category="SECURITY_EXCEPTION",
            extracted_data={"error": "Signature mismatch"},
            action=Action.QUARANTINE,
            reason="Webhook signature verification failed",
            source="LIVE_WEBHOOK",
            raw_evidence={"error": str(e), "event": "signature_mismatch"},
        )
        raise HTTPException(status_code=400, detail="Invalid signature")

    payload = json.loads(raw_body)
    
    # Block 2: Timestamp Skew Check (prevent replay attacks)
    created_at = payload.get("created_at")
    if created_at:
        skew = datetime.datetime.utcnow().timestamp() - created_at
        if skew > 300 or skew < -300:  # 5 minutes
            conn.close()
            raise HTTPException(status_code=400, detail="Payload timestamp expired (skew > 5 mins)")

    event_id = request.headers.get("x-razorpay-event-id", "unknown")

    already_processed = conn.execute(
        "SELECT 1 FROM processed_events WHERE merchant_id = ? AND event_id = ? LIMIT 1", (merchant_id, event_id)
    ).fetchone()

    if already_processed:
        conn.close()
        return {"status": "ignored", "reason": "duplicate"}

    # Mark event as processed (synchronous dedup lock)
       # Mark event as processed (synchronous dedup lock)
    try:
        with conn:
            conn.execute(
                "INSERT INTO processed_events (merchant_id, event_id, timestamp) VALUES (?, ?, ?)",
                (merchant_id, event_id, datetime.datetime.utcnow().isoformat()),
            )
    except Exception:
        conn.close()
        return {"status": "ignored", "reason": "duplicate"}
    conn.close()

    # Block 2: Async Webhook Processing
    background_tasks.add_task(process_webhook_event, merchant_id, payload)
    
    return {"status": "ok", "message": "processing"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)