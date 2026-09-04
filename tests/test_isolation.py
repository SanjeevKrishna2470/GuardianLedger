import os
import sys
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from api.main import app
from report.db import get_db

client = TestClient(app)

def create_merchant_and_user(email: str, name: str):
    # Call signup API
    resp = client.post("/api/signup", json={"email": email, "password": "password123", "merchant_name": name})
    assert resp.status_code == 200
    data = resp.json()
    return data["merchant_id"], data["access_token"]

def insert_transaction(merchant_id: str, txn_ref: str):
    conn = get_db()
    with conn:
        conn.execute(
            "INSERT INTO transactions (merchant_id, timestamp, txn_ref, source, m4_action) VALUES (?, '2026-01-01', ?, 'BATCH', 'REVIEW')",
            (merchant_id, txn_ref)
        )
    conn.close()

def test_tenant_isolation():
    """Test that Merchant A cannot see Merchant B's transactions."""
    # 1. Create two merchants
    merchant_a, token_a = create_merchant_and_user("merch_a@test.com", "Merchant A")
    merchant_b, token_b = create_merchant_and_user("merch_b@test.com", "Merchant B")
    
    # 2. Insert dummy transactions
    insert_transaction(merchant_a, "TXN_A_1")
    insert_transaction(merchant_b, "TXN_B_1")
    
    # 3. Fetch A's queue with A's token
    res_a = client.get("/api/queue", headers={"Authorization": f"Bearer {token_a}"})
    assert res_a.status_code == 200
    queue_a = res_a.json()
    assert len(queue_a) == 1
    assert queue_a[0]["txn_ref"] == "TXN_A_1"
    
    # 4. Fetch B's queue with A's token (Wait, A doesn't request B's queue explicitly, the queue endpoint just returns the logged in user's queue. We need to verify B's transactions don't leak).
    # Step 3 verified it only returned 1 transaction, which is A's. Let's explicitly check if B's is in A's queue.
    assert "TXN_B_1" not in [t["txn_ref"] for t in queue_a]
    
    # 5. Fetch all transactions for A
    res_all_a = client.get("/api/transactions", headers={"Authorization": f"Bearer {token_a}"})
    all_a = res_all_a.json()
    assert len(all_a) == 1
    assert all_a[0]["txn_ref"] == "TXN_A_1"
    
    # 6. Fetch dashboard for A
    res_dash_a = client.get("/api/dashboard", headers={"Authorization": f"Bearer {token_a}"})
    dash_a = res_dash_a.json()
    assert dash_a["total_processed"] == 1
    
    # Prove they are isolated
    res_b = client.get("/api/transactions", headers={"Authorization": f"Bearer {token_b}"})
    all_b = res_b.json()
    assert len(all_b) == 1
    assert all_b[0]["txn_ref"] == "TXN_B_1"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
