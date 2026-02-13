import json

from agents.orchestrator import call_tool, invoke_json, log_agent, recent_conversation
from prompts import role_prompt


def accomodations_agent(state: dict) -> dict:
    log_agent("accomodations_agent", "Evaluating stay options against preferences")
    req = state["user_requirements"]
    destination = req["location_preference"]
    days = req["days"]
    options = call_tool(state, "accomodations_agent", "AccomsAPI", destination)
    search_hits = call_tool(state, "accomodations_agent", "WebSearchAPI", f"Best areas to stay in {destination}", 5)
    transit_hint = call_tool(state, "accomodations_agent", "MapsAPI", "airport", destination)
    review_hits = call_tool(state, "accomodations_agent", "ReviewsAPI", f"Hotels in {destination}", 5)
    optimization_hints = state.get("optimization_hints", {})

    system = role_prompt("Accomodations Agent")
    user = (
        "Use AccomsAPI data and user accommodation preferences.\n"
        "Return JSON with keys: selected_stay, area_notes, tradeoffs, estimated_total_sgd.\n"
        f"Requirements: {json.dumps(req)}\n"
        f"Feedback: {state.get('feedback', '')}\n"
        f"Optimization hints: {json.dumps(optimization_hints)}\n"
        f"Prior team messages: {recent_conversation(state)}\n"
        f"AccomsAPI: {json.dumps(options)}\n"
        f"WebSearchAPI: {json.dumps(search_hits)}\n"
        f"MapsAPI: {json.dumps(transit_hint)}\n"
        f"ReviewsAPI: {json.dumps(review_hits)}"
    )
    plan = invoke_json(system, user)
    if not plan:
        log_agent("accomodations_agent", "LLM output invalid JSON, using deterministic fallback")
        selected = options[0] if optimization_hints.get("target_reduction_sgd", 0) > 0 else options[1]
        plan = {
            "selected_stay": selected,
            "area_notes": "Choose well-connected area to control commute costs.",
            "tradeoffs": "Selected option balances budget and access to attractions.",
            "estimated_total_sgd": selected["nightly_rate_sgd"] * days,
        }

    state["accomodations_plan"] = plan
    log_agent(
        "accomodations_agent",
        f"Estimated accommodation total SGD: {plan.get('estimated_total_sgd', 'N/A')}",
    )
    state.setdefault("conversation", []).append(("accomodations_agent", plan))
    return state
