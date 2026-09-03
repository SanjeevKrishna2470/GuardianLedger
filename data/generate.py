import pandas as pd
import random
from datetime import datetime, timedelta

def generate_base_data(num_records=50):
    gateway_data = []
    bank_data = []
    ledger_data = []
    answer_key = []

    base_time = datetime(2026, 9, 1)

    for i in range(num_records):
        txn_ref = f"TXN-{1000 + i}"
        amount = round(random.uniform(10.0, 5000.0), 2)
        fee = round(amount * 0.02, 2)
        net_amount = round(amount - fee, 2)
        
        # Base Clean Match
        gateway_data.append({
            "txn_id": txn_ref,
            "amount": amount,
            "currency": "INR",
            "customer_id": f"CUST-{random.randint(100, 999)}",
            "timestamp": base_time.isoformat(),
            "status": "success"
        })
        
        bank_data.append({
            "settlement_id": f"SETT-{1000 + i}",
            "txn_ref": txn_ref,
            "settled_amount": net_amount,
            "settlement_date": (base_time + timedelta(days=2)).strftime("%Y-%m-%d"),
            "fee_deducted": fee
        })
        
        ledger_data.append({
            "entry_id": f"LEDG-{1000 + i}",
            "expected_txn_ref": txn_ref,
            "expected_amount": net_amount,
            "booked_date": (base_time + timedelta(days=2)).strftime("%Y-%m-%d"),
            "account": "main_account"
        })
        
        answer_key.append({
            "txn_ref": txn_ref,
            "true_category": "CLEAN",
            "ground_truth_match": True
        })

    # Inject mismatches (replace some clean records)
    
    # 1. Timing lag (Index 5)
    bank_data[5]["settlement_date"] = (base_time + timedelta(days=10)).strftime("%Y-%m-%d")
    answer_key[5] = {"txn_ref": bank_data[5]["txn_ref"], "true_category": "TIMING_LAG", "ground_truth_match": False}
    
    # 2. Fee mismatch (Index 10)
    bank_data[10]["fee_deducted"] = round(bank_data[10]["fee_deducted"] + 10.0, 2)
    bank_data[10]["settled_amount"] = round(gateway_data[10]["amount"] - bank_data[10]["fee_deducted"], 2)
    answer_key[10] = {"txn_ref": bank_data[10]["txn_ref"], "true_category": "FEE_MISMATCH", "ground_truth_match": False}
    
    # 3. Duplicate ledger entry (Index 15)
    ledger_data.append(ledger_data[15].copy())
    ledger_data[-1]["entry_id"] = f"LEDG-{1000 + 15}-DUP"
    answer_key[15] = {"txn_ref": bank_data[15]["txn_ref"], "true_category": "DUPLICATE", "ground_truth_match": False}
    
    # 4. Orphan (gateway record with no settlement/ledger) (Index 20)
    orphan_ref = bank_data[20]["txn_ref"]
    bank_data.pop(20)
    ledger_data.pop(20)
    answer_key[20] = {"txn_ref": orphan_ref, "true_category": "ORPHAN", "ground_truth_match": False}
    
    # 5. Amount drift (partial refund pattern) (Index 25)
    bank_data[24]["settled_amount"] = round(bank_data[24]["settled_amount"] - 50.0, 2)
    answer_key[25] = {"txn_ref": bank_data[24]["txn_ref"], "true_category": "AMOUNT_DRIFT", "ground_truth_match": False}
    
    return gateway_data, bank_data, ledger_data, answer_key

def main():
    import os
    os.makedirs('data', exist_ok=True)
    gateway, bank, ledger, ans = generate_base_data()
    
    pd.DataFrame(gateway).to_csv("data/gateway_transactions.csv", index=False)
    pd.DataFrame(bank).to_csv("data/bank_settlement.csv", index=False)
    pd.DataFrame(ledger).to_csv("data/ledger_entries.csv", index=False)
    pd.DataFrame(ans).to_csv("data/answer_key.csv", index=False)
    print("M0 data generation complete.")

if __name__ == "__main__":
    main()
