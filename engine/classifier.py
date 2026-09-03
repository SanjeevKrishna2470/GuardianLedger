import pandas as pd

def check_duplicate(record):
    if len(record['ledger_record']) > 1 or len(record['bank_record']) > 1:
        return "DUPLICATE"
    return None

def check_orphan(record):
    if len(record['gateway_record']) > 0 and len(record['bank_record']) == 0 and len(record['ledger_record']) == 0:
        return "ORPHAN"
    return None

def check_timing_lag(record):
    if len(record['gateway_record']) == 1 and len(record['bank_record']) == 1:
        gw_date = pd.to_datetime(record['gateway_record'][0]['timestamp']).date()
        bank_date = pd.to_datetime(record['bank_record'][0]['settlement_date']).date()
        if abs((bank_date - gw_date).days) > 5:
            return "TIMING_LAG"
    return None

def check_fee_mismatch(record):
    if len(record['gateway_record']) == 1 and len(record['bank_record']) == 1 and len(record['ledger_record']) == 1:
        gw_amt = float(record['gateway_record'][0]['amount'])
        bank_net = float(record['bank_record'][0]['settled_amount'])
        fee = float(record['bank_record'][0]['fee_deducted'])
        ledger_amt = float(record['ledger_record'][0]['expected_amount'])
        if abs(gw_amt - (bank_net + fee)) <= 0.01 and abs(bank_net - ledger_amt) > 0.01:
            return "FEE_MISMATCH"
    return None

def check_amount_drift(record):
    if len(record['gateway_record']) == 1 and len(record['bank_record']) == 1:
        gw_amt = float(record['gateway_record'][0]['amount'])
        bank_net = float(record['bank_record'][0]['settled_amount'])
        fee = float(record['bank_record'][0]['fee_deducted'])
        if abs(gw_amt - (bank_net + fee)) > 0.01:
            return "AMOUNT_DRIFT"
    return None

def classify_exception(record):
    if record['match_status'] != "NEEDS_CLASSIFICATION":
        return None
        
    # Chain of responsibility
    checks = [
        check_duplicate,
        check_orphan,
        check_timing_lag,
        check_fee_mismatch,
        check_amount_drift
    ]
    
    for check in checks:
        result = check(record)
        if result:
            return result
            
    return "UNEXPLAINED"

if __name__ == "__main__":
    from matcher import run_matcher
    results = run_matcher("data/gateway_transactions.csv", "data/bank_settlement.csv", "data/ledger_entries.csv")
    
    classifications = {}
    for r in results:
        if r['match_status'] == 'NEEDS_CLASSIFICATION':
            cat = classify_exception(r)
            classifications[r['txn_ref']] = cat
            
    ans = pd.read_csv("data/answer_key.csv")
    
    matches = 0
    total = len(classifications)
    for txn_ref, cat in classifications.items():
        true_cat = ans[ans['txn_ref'] == txn_ref]['true_category'].values[0]
        if cat == true_cat:
            matches += 1
        else:
            print(f"Mismatch for {txn_ref}: Got {cat}, Expected {true_cat}")
            
    print(f"M2 Results: correctly classified {matches}/{total} exceptions.")
    if matches == total and total == 5:
        print("Milestone Check: PASSED")
    else:
        print("Milestone Check: FAILED")
