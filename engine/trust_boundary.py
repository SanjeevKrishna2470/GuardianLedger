from enum import Enum
import re
import json

# The Privileged-Action Veto / Hard Allowlist
class Action(Enum):
    MATCH = "MATCH"
    REVIEW = "REVIEW"
    EXCEPTION = "EXCEPTION"
    QUARANTINE = "QUARANTINE"

def check_source_agreement(record, proposed_match=None):
    """
    Do independent sources actually corroborate the proposed match?
    For MVP, we just verify that if it's a MATCH, all sources were present.
    """
    if proposed_match == Action.MATCH:
        if not (record.get('gateway_record') and record.get('bank_record') and record.get('ledger_record')):
            return False, "Missing source corroboration for MATCH"
    return True, "Source agreement ok"

def check_schema_validity(evidence):
    """
    Does the evidence come from an expected, structurally valid source?
    """
    if not isinstance(evidence, (dict, list, str)):
        return False, "Invalid schema type"
    return True, "Schema ok"

def scan_for_instructions(text):
    """
    Keyword/pattern matching against raw text for imperative verbs 
    and privileged-action language.
    """
    if not isinstance(text, str):
        text = json.dumps(text)
        
    text_lower = text.lower()
    
    # Simple list of suspicious verbs and patterns
    suspicious_patterns = [
        r"\btransfer\b",
        r"\boverride\b",
        r"\bmark_settled\b",
        r"\bignore previous instructions\b",
        r"\bforce\b",
        r"\bexecute\b"
    ]
    
    for pattern in suspicious_patterns:
        if re.search(pattern, text_lower):
            return False, f"Instruction pattern detected: {pattern}"
            
    return True, "No instructions detected"

def verify_proposal(record, raw_evidence, proposed_action: Action):
    """
    The main Trust Boundary gate.
    Passes through the 4 checks and returns (Action, reason).
    """
    # 1. Privileged-action veto
    if not isinstance(proposed_action, Action):
        return Action.QUARANTINE, "Invalid action type (Vetoed)"
        
    # 2. Schema/provenance validity
    valid_schema, schema_reason = check_schema_validity(raw_evidence)
    if not valid_schema:
        return Action.QUARANTINE, f"Schema invalid: {schema_reason}"
        
    # 3. Source agreement check
    agrees, agreement_reason = check_source_agreement(record, proposed_action)
    if not agrees:
        return Action.QUARANTINE, f"Source agreement failed: {agreement_reason}"
        
    # 4. Instruction-pattern scan
    safe, scan_reason = scan_for_instructions(raw_evidence)
    if not safe:
        return Action.QUARANTINE, f"Security scan failed: {scan_reason}"
        
    # If all checks pass, allow the proposed action
    return proposed_action, "Passed all verifications"

if __name__ == "__main__":
    # Milestone Check
    print("Running M4 Milestone Check...")
    
    # Test 1: Poisoned fixture
    with open("data/poisoned_fixture.json") as f:
        poisoned_data = json.load(f)
        
    record = {}
    action, reason = verify_proposal(record, poisoned_data, Action.REVIEW)
    print(f"Poisoned Fixture Result: {action.name}, Reason: {reason}")
    assert action == Action.QUARANTINE
    
    # Test 2: Legitimate ambiguous case
    legit_evidence = {"notes": "Customer name misspelled slightly, manual review needed."}
    action, reason = verify_proposal(record, legit_evidence, Action.REVIEW)
    print(f"Legitimate Case Result: {action.name}, Reason: {reason}")
    assert action == Action.REVIEW
    
    print("Milestone Check: PASSED")
