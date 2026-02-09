def budget(state):
    trips = state.get("trip_options", [])
    est = trips[0]["estimated_cost"] if trips else "N/A"
    msg = f"Estimated budget ~ ${est} USD (subject to hotel/flight choices)."
    print(f"💰 Budget Analyst: {msg}")
    state["conversation"].append(("budget_analyst", msg))
    state["budget_done"] = True
    return state
