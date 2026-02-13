from prompts import role_prompt
from agents.orchestrator import invoke_json, log_agent, recent_conversation


def _get_cost(plan: dict) -> float:
    value = plan.get("estimated_total_sgd", 0)
    try:
        return float(value)
    except Exception:
        return 0.0


def budget_agent(state: dict) -> dict:
    log_agent("budget_agent", "Reconciling all agent estimates against user budget")
    req = state["user_requirements"]
    total_budget = float(req["budget_sgd"])

    flight_cost = _get_cost(state.get("flight_plan", {}))
    food_cost = _get_cost(state.get("food_plan", {}))
    location_cost = _get_cost(state.get("locations_plan", {}))
    accom_cost = _get_cost(state.get("accomodations_plan", {}))
    projected_total = flight_cost + food_cost + location_cost + accom_cost

    plan = invoke_json(
        role_prompt("Budget Agent"),
        (
            "Return JSON with keys: projected_total_sgd, within_budget, buffer_sgd, adjustment_advice.\n"
            f"Budget SGD: {total_budget}\n"
            f"Costs: flight={flight_cost}, food={food_cost}, location={location_cost}, accomodations={accom_cost}\n"
            f"Feedback: {state.get('feedback', '')}\n"
            f"Prior team messages: {recent_conversation(state)}"
        ),
    )
    if not plan:
        log_agent("budget_agent", "LLM output invalid JSON, using deterministic fallback")
        buffer_sgd = round(total_budget - projected_total, 2)
        plan = {
            "projected_total_sgd": round(projected_total, 2),
            "within_budget": projected_total <= total_budget,
            "buffer_sgd": buffer_sgd,
            "adjustment_advice": "Use budget flights or reduce premium meals if buffer is negative.",
        }

    projected = float(plan.get("projected_total_sgd", projected_total))
    within_budget = bool(plan.get("within_budget", projected <= total_budget))
    shortfall = max(0.0, round(projected - total_budget, 2))
    state["optimization_hints"] = {
        "target_reduction_sgd": shortfall,
        "flight": "Prefer 1-stop economy fare with lower total price.",
        "accomodations": "Move to budget or lower nightly rate area with acceptable commute.",
        "food": "Increase low-cost local meals and reduce premium dining frequency.",
        "locations": "Prioritize free/low-ticket attractions and cluster nearby activities.",
    }
    if not within_budget:
        log_agent(
            "budget_agent",
            f"Budget over by SGD {shortfall}. Generated optimization_hints for next round.",
        )

    state["budget_plan"] = plan
    log_agent(
        "budget_agent",
        f"Projected total SGD: {plan.get('projected_total_sgd', 'N/A')}, within budget: {plan.get('within_budget', 'N/A')}",
    )
    state.setdefault("conversation", []).append(("budget_agent", plan))
    return state
