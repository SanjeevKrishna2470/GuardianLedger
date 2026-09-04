import json
import os
import sqlite3
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from report.db import get_db, _PROJECT_ROOT

def _row_to_dict(row) -> dict:
    d = dict(row)
    for field in ("m3_extracted", "raw_evidence"):
        if d.get(field) and isinstance(d[field], str):
            try:
                d[field] = json.loads(d[field])
            except Exception:
                pass
    return d

app = FastAPI(title="Guardian Ledger API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

class ActionRequest(BaseModel):
    txn_ref: str
    decision: str  # "approve" or "reject"
    reviewer_note: str = ""

@app.post("/api/run-pipeline")
def run_pipeline_endpoint():
    try:
        from run import main as run_pipeline_main
        run_pipeline_main()
        report_path = os.path.join(DATA_DIR, "report.json")
        if os.path.exists(report_path):
            with open(report_path) as f:
                return json.load(f)
        return {"status": "ok", "message": "Pipeline completed successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/dashboard")
def get_dashboard():
    report_path = os.path.join(DATA_DIR, "report.json")
    if not os.path.exists(report_path):
        return {"error": "No report found. Run the pipeline first."}
    with open(report_path) as f:
        return json.load(f)

@app.get("/api/queue")
def get_review_queue():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM transactions WHERE m4_action IN ('REVIEW','EXCEPTION','QUARANTINE') ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]

@app.get("/api/transactions")
def get_all_transactions():
    conn = get_db()
    rows = conn.execute("SELECT * FROM transactions ORDER BY id DESC").fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]

class SimulateRequest(BaseModel):
    type: str

import uuid
import datetime
import random
import sys

# Ensure root path is accessible
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from engine.classifier import classify_exception
from engine.trust_boundary import verify_proposal, Action
from engine.router import route_action
from report.audit_log import logger
from report.report import generate_report

@app.post("/api/simulate")
def simulate_transaction(req: SimulateRequest):
    txn_ref = f"SIM-{uuid.uuid4().hex[:8]}"
    base_amount = round(random.uniform(50.0, 500.0), 2)
    today = datetime.date.today()
    
    gw_amt = base_amount
    fee = round(base_amount * 0.02, 2)
    bank_amt = round(base_amount - fee, 2)
    ledger_amt = bank_amt
    
    gw_date = today
    bank_date = today + datetime.timedelta(days=1)
    
    if req.type == "FEE_MISMATCH":
        bank_amt -= 5.0
    elif req.type == "TIMING_LAG":
        bank_date = today + datetime.timedelta(days=10)
    
    gw_rec = {
        'amount': gw_amt, 'currency': 'USD', 'timestamp': f"{gw_date}T10:00:00Z", 'status': 'COMPLETED'
    }
    bank_rec = {
        'settlement_id': f"SET-{uuid.uuid4().hex[:6]}", 'settled_amount': bank_amt, 'settlement_date': str(bank_date), 'fee_deducted': fee
    }
    ledger_rec = {
        'entry_id': f"LEDG-{uuid.uuid4().hex[:6]}", 'expected_amount': ledger_amt, 'booked_date': str(today), 'account': 'Revenue'
    }
    
    if req.type == "ORPHAN":
        bank_rec = None
        ledger_rec = None
        
    status = "MATCHED"
    if req.type != "CLEAN":
        status = "NEEDS_CLASSIFICATION"
        
    record = {
        'txn_ref': txn_ref,
        'match_status': status,
        'gateway_record': [gw_rec] if gw_rec else [],
        'bank_record': [bank_rec] if bank_rec else [],
        'ledger_record': [ledger_rec] if ledger_rec else []
    }
    
    category = None
    extracted_data = None
    
    if status == "NEEDS_CLASSIFICATION":
        category = classify_exception(record)
        proposed_action = Action.EXCEPTION if category else Action.REVIEW
    else:
        proposed_action = Action.MATCH
        
    final_action, reason = verify_proposal(record, record, proposed_action)
    route_action(final_action)
    
    # Overwrite the logger file if needed? No, logger appends.
    # But logger needs DATA_DIR? logger uses "data/audit_log.jsonl".
    # main.py is run from root or api? Usually root. 
    logger.log_transaction(
        txn_ref=txn_ref,
        match_result=status,
        category=category,
        extracted_data=extracted_data,
        action=final_action,
        reason=reason,
        source="SIMULATION",
        raw_evidence={
            "gateway_record": gw_rec,
            "bank_record": bank_rec,
            "ledger_record": ledger_rec
        }
    )
    
    generate_report()
    
    return {"status": "ok", "txn_ref": txn_ref, "type": req.type, "action": final_action.value}

@app.post("/api/action")
def post_action(req: ActionRequest):
    conn = get_db()
    with conn:
        conn.execute(
            "INSERT INTO decisions (timestamp, txn_ref, decision, reviewer_note) VALUES (?, ?, ?, ?)",
            (datetime.datetime.utcnow().isoformat(), req.txn_ref, req.decision, req.reviewer_note),
        )
    conn.close()
    return {"status": "ok", "decision": req.decision, "txn_ref": req.txn_ref}

# --- Razorpay Integration ---

import razorpay
from fastapi import Request, HTTPException, Header

def get_razorpay_client():
    key_id = os.environ.get("RAZORPAY_KEY_ID")
    key_secret = os.environ.get("RAZORPAY_KEY_SECRET")
    if not key_id or not key_secret:
        raise HTTPException(status_code=500, detail="Razorpay credentials missing in environment variables.")
    return razorpay.Client(auth=(key_id, key_secret))

class OrderRequest(BaseModel):
    amount: int
    currency: str = "INR"

@app.post("/api/orders")
def create_order(req: OrderRequest):
    client = get_razorpay_client()
    key_id = os.environ.get("RAZORPAY_KEY_ID", "")
    data = {
        "amount": req.amount,
        "currency": req.currency,
        "receipt": f"receipt_{uuid.uuid4().hex[:8]}",
        "payment_capture": 1
    }
    try:
        order = client.order.create(data=data)
        return {
            "order_id": order["id"],
            "amount": order["amount"],
            "currency": order["currency"],
            "key_id": key_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class VerifyPaymentRequest(BaseModel):
    payment_id: str
    order_id: str
    signature: str

@app.post("/api/verify-payment")
def verify_payment(req: VerifyPaymentRequest):
    client = get_razorpay_client()
    try:
        client.utility.verify_payment_signature({
            'razorpay_order_id': req.order_id,
            'razorpay_payment_id': req.payment_id,
            'razorpay_signature': req.signature
        })
    except Exception as e:
        logger.log_transaction(
            txn_ref=req.payment_id,
            match_result="FAILED",
            category="SECURITY_EXCEPTION",
            extracted_data={"order_id": req.order_id, "error": str(e)},
            action=Action.QUARANTINE,
            reason="Checkout payment signature verification failed",
            source="LIVE_CHECKOUT",
            raw_evidence={"error": str(e), "order_id": req.order_id, "signature": req.signature}
        )
        raise HTTPException(status_code=400, detail="Invalid payment signature")

    if not logger.is_logged(req.payment_id):
        logger.log_transaction(
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
                    "status": "captured"
                },
                "event": "payment.verified"
            }
        )
        generate_report()

    return {"status": "ok", "message": "Payment verified and recorded", "txn_ref": req.payment_id}

@app.post("/api/webhooks/razorpay")
async def razorpay_webhook(request: Request, x_razorpay_signature: str = Header(None)):
    raw_body = await request.body()
    webhook_secret = os.environ.get("RAZORPAY_WEBHOOK_SECRET")
    
    if not webhook_secret:
        print("WARNING: Webhook received but RAZORPAY_WEBHOOK_SECRET not set.")
        raise HTTPException(status_code=500, detail="Webhook secret not configured")
        
    if not x_razorpay_signature:
        raise HTTPException(status_code=400, detail="Missing signature")
        
    client = get_razorpay_client()
    try:
        # Feature 3: Signature Verification
        client.utility.verify_webhook_signature(raw_body.decode('utf-8'), x_razorpay_signature, webhook_secret)
    except Exception as e:
        print(f"SECURITY EXCEPTION: Signature mismatch! {e}")
        # Log the security exception
        logger.log_transaction(
            txn_ref="UNKNOWN",
            match_result="FAILED",
            category="SECURITY_EXCEPTION",
            extracted_data={"error": "Signature mismatch"},
            action=Action.QUARANTINE,
            reason="Webhook signature verification failed",
            source="LIVE_WEBHOOK",
            raw_evidence={"error": str(e), "event": "signature_mismatch"}
        )
        raise HTTPException(status_code=400, detail="Invalid signature")

    # Feature 4: Dedup + Ordering
    payload = json.loads(raw_body)
    event_id = request.headers.get("x-razorpay-event-id", "unknown")
    
    # Dedup via processed_events table
    conn = get_db()
    already_processed = conn.execute(
        "SELECT 1 FROM processed_events WHERE event_id = ? LIMIT 1", (event_id,)
    ).fetchone()

    if already_processed:
        conn.close()
        print(f"DUPLICATE EXCEPTION: Event ID {event_id} already processed.")
        logger.log_transaction(
            txn_ref=payload.get("payload", {}).get("payment", {}).get("entity", {}).get("id", "UNKNOWN"),
            match_result="FAILED",
            category="DUPLICATE",
            extracted_data={"event_id": event_id},
            action=Action.EXCEPTION,
            reason=f"Duplicate webhook event: {event_id}",
            source="LIVE_WEBHOOK",
            raw_evidence={"event_id": event_id, "event": "duplicate_webhook"}
        )
        return {"status": "ignored", "reason": "duplicate"}

    # Mark event as processed
    with conn:
        conn.execute(
            "INSERT INTO processed_events (event_id, timestamp) VALUES (?, ?)",
            (event_id, datetime.datetime.utcnow().isoformat()),
        )
    conn.close()

    event_type = payload.get("event")
    print(f"Processing genuine webhook event: {event_type} - {event_id}")

    # Process events
    if event_type in ("payment.captured", "payment.authorized"):
        payment_entity = payload["payload"]["payment"]["entity"]
        txn_ref = payment_entity["id"]
        
        if not logger.is_logged(txn_ref):
            logger.log_transaction(
                txn_ref=txn_ref,
                match_result="MATCHED",
                category="Settlement",
                extracted_data={"event": event_type, "amount": payment_entity.get("amount", 0) / 100},
                action=Action.MATCH,
                reason=f"Razorpay {event_type} via live webhook",
                source="LIVE_WEBHOOK",
                raw_evidence={
                    "gateway_record": payment_entity,
                    "event": event_type,
                    "order_id": payment_entity.get("order_id")
                }
            )
        
    elif event_type == "payment.failed":
        payment_entity = payload["payload"]["payment"]["entity"]
        txn_ref = payment_entity["id"]
        
        logger.log_transaction(
            txn_ref=txn_ref,
            match_result="FAILED",
            category="PAYMENT_FAILED",
            extracted_data={"event": event_type, "error_description": payment_entity.get("error_description")},
            action=Action.EXCEPTION,
            reason=f"Razorpay payment failed via live webhook: {payment_entity.get('error_description', 'unknown')}",
            source="LIVE_WEBHOOK",
            raw_evidence={
                "gateway_record": payment_entity,
                "event": event_type,
            }
        )
        
    elif event_type == "refund.processed":
        refund_entity = payload["payload"]["refund"]["entity"]
        txn_ref = refund_entity["payment_id"]
        
        # Log refund
        logger.log_transaction(
            txn_ref=txn_ref,
            match_result="NEEDS_CLASSIFICATION",
            category="REFUND",
            extracted_data={"event": "refund.processed", "refund_id": refund_entity.get("id"), "amount": refund_entity.get("amount", 0) / 100},
            action=Action.REVIEW,
            reason="Refund processed by Razorpay via live webhook",
            source="LIVE_WEBHOOK",
            raw_evidence={
                "gateway_record": refund_entity,
                "event": "refund.processed",
                "payment_id": refund_entity.get("payment_id")
            }
        )

    generate_report()
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
