import time
import json
import os
import sys

# Add root to path if needed, but running from root works automatically.

from data.generate import main as generate_data
from engine.matcher import run_matcher
from engine.classifier import classify_exception
from engine.extractor import extract_evidence
from engine.trust_boundary import verify_proposal, Action
from engine.router import route_action
from report.audit_log import logger
from report.report import generate_report

def main():
    print("Starting Guardian Ledger end-to-end pipeline...")
    start_time = time.time()
    
    # Run M0: Generate data
    print("[M0] Generating synthetic data batches...")
    generate_data()
    
    # Run M1: Deterministic matching
    print("[M1] Running deterministic matcher...")
    m1_results = run_matcher("data/gateway_transactions.csv", "data/bank_settlement.csv", "data/ledger_entries.csv")
    
    # Load poisoned fixture for the one M3 test
    with open("data/poisoned_fixture.json") as f:
        poisoned_fixture = json.dumps(json.load(f))

    processed_count = 0
    for record in m1_results:
        txn_ref = record['txn_ref']
        status = record['match_status']
        
        category = None
        extracted_data = None
        proposed_action = None
        
        # M2: Classifier
        if status == "NEEDS_CLASSIFICATION":
            category = classify_exception(record)
            if category:
                proposed_action = Action.EXCEPTION
            else:
                proposed_action = Action.REVIEW
        else:
            proposed_action = Action.MATCH

        # M3: LLM Extraction (Mock injection for the last record as a demo)
        # We'll pretend the last record is the messy one we need M3 for
        raw_evidence = record
        if processed_count == len(m1_results) - 1:
            print(f"[M3] Running evidence extraction on adversarial input for {txn_ref}...")
            # We feed the poisoned fixture to the extractor
            proposal = extract_evidence(poisoned_fixture)
            extracted_data = proposal.model_dump()
            raw_evidence = poisoned_fixture
            proposed_action = Action.REVIEW # M3 proposes REVIEW
            
        # M4: Trust Boundary
        final_action, reason = verify_proposal(record, raw_evidence, proposed_action)
        
        # M5: Action Router
        outcome = route_action(final_action)
        
        # M6: Audit Logging
        logger.log_transaction(
            txn_ref=txn_ref,
            match_result=status,
            category=category,
            extracted_data=extracted_data,
            action=final_action,
            reason=reason
        )
        processed_count += 1
        
    end_time = time.time()
    print("[M6] Generating report...")
    generate_report(start_time=start_time, end_time=end_time)
    print("Pipeline complete.")

if __name__ == "__main__":
    main()
