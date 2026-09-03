from engine.trust_boundary import Action

def route_action(action: Action):
    """
    Takes M4's verdict and routes to exactly one of four outcomes.
    No other code path exists.
    """
    if not isinstance(action, Action):
        raise ValueError(f"Router received invalid action type: {type(action)}")
        
    if action == Action.MATCH:
        return "POST"
    elif action == Action.REVIEW:
        return "REVIEW"
    elif action == Action.EXCEPTION:
        return "EXCEPTION"
    elif action == Action.QUARANTINE:
        return "QUARANTINE"
        
    raise ValueError("Fell through router without hitting a valid action.")

if __name__ == "__main__":
    # Milestone Check
    print("Running M5 Milestone Check...")
    
    # Confirm all outcomes are reachable
    actions = [Action.MATCH, Action.REVIEW, Action.EXCEPTION, Action.QUARANTINE]
    routed_counts = {"POST": 0, "REVIEW": 0, "EXCEPTION": 0, "QUARANTINE": 0}
    
    for a in actions:
        outcome = route_action(a)
        routed_counts[outcome] += 1
        
    for outcome, count in routed_counts.items():
        assert count == 1, f"Outcome {outcome} was not reached exactly once."
        
    print(f"Routed counts: {routed_counts}")
    print("Milestone Check: PASSED. All four outcomes are reachable and no fallthrough.")
