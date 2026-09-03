import pandas as pd
import json

def run_matcher(gateway_file, bank_file, ledger_file):
    gw = pd.read_csv(gateway_file)
    bank = pd.read_csv(bank_file)
    ledger = pd.read_csv(ledger_file)
    
    # Rename columns to join easily
    gw = gw.rename(columns={'txn_id': 'txn_ref'})
    ledger = ledger.rename(columns={'expected_txn_ref': 'txn_ref'})
    
    # Merge all three on txn_ref
    # We do an outer join to catch orphans and duplicates
    # For ledger, since there might be duplicates, let's keep all
    merged = gw.merge(bank, on='txn_ref', how='outer', suffixes=('_gw', '_bank'))
    merged = merged.merge(ledger, on='txn_ref', how='outer', suffixes=('', '_ledger'))
    
    results = []
    
    # Iterate through each unique txn_ref
    for txn_ref, group in merged.groupby('txn_ref'):
        # Check if it's a clean 1-to-1-to-1 match
        if len(group) == 1:
            row = group.iloc[0]
            # Check for nulls (missing in one of the sources)
            if pd.isna(row['amount']) or pd.isna(row['settled_amount']) or pd.isna(row['expected_amount']):
                status = "NEEDS_CLASSIFICATION"
            else:
                # Tolerance check
                gw_amt = float(row['amount'])
                bank_net = float(row['settled_amount'])
                fee = float(row['fee_deducted'])
                ledger_amt = float(row['expected_amount'])
                
                gw_date = pd.to_datetime(row['timestamp']).date()
                bank_date = pd.to_datetime(row['settlement_date']).date()
                
                # Check amount equality and date tolerance (<= 5 days)
                amount_match = abs(gw_amt - (bank_net + fee)) < 0.01 and abs(bank_net - ledger_amt) < 0.01
                date_match = abs((bank_date - gw_date).days) <= 5
                
                if amount_match and date_match:
                    status = "MATCHED"
                else:
                    status = "NEEDS_CLASSIFICATION"
        else:
            # Duplicates or multiples
            status = "NEEDS_CLASSIFICATION"
            row = group.iloc[0] # just grab first for passing along
            
        record = {
            'txn_ref': txn_ref,
            'match_status': status,
            'gateway_record': group[['amount', 'currency', 'timestamp', 'status']].to_dict('records') if not pd.isna(group['amount'].iloc[0]) else [],
            'bank_record': group[['settlement_id', 'settled_amount', 'settlement_date', 'fee_deducted']].to_dict('records') if not pd.isna(group['settled_amount'].iloc[0]) else [],
            'ledger_record': group[['entry_id', 'expected_amount', 'booked_date', 'account']].to_dict('records') if not pd.isna(group['expected_amount'].iloc[0]) else []
        }
        results.append(record)
        
    return results

if __name__ == "__main__":
    import sys
    # For milestone check:
    results = run_matcher("data/gateway_transactions.csv", "data/bank_settlement.csv", "data/ledger_entries.csv")
    
    matched = sum(1 for r in results if r['match_status'] == 'MATCHED')
    needs_class = sum(1 for r in results if r['match_status'] == 'NEEDS_CLASSIFICATION')
    
    ans = pd.read_csv("data/answer_key.csv")
    ans_clean = len(ans[ans['true_category'] == 'CLEAN'])
    ans_mismatch = len(ans[ans['true_category'] != 'CLEAN'])
    
    print(f"M1 Results: MATCHED={matched}, NEEDS_CLASSIFICATION={needs_class}")
    print(f"Answer Key: CLEAN={ans_clean}, MISMATCH={ans_mismatch}")
    
    if matched == ans_clean and needs_class == ans_mismatch:
        print("Milestone Check: PASSED")
    else:
        print("Milestone Check: FAILED")
