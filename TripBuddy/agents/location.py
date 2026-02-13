import json

from agents.orchestrator import call_tool, invoke_json, log_agent, recent_conversation
from prompts import role_prompt


def locations_agent(state: dict) -> dict:
    log_agent("locations_agent", "Building attraction shortlist from location preference")
    req = state["user_requirements"]
    destination = req["location_preference"]
    attractions = call_tool(state, "locations_agent", "TouristAttractionAPI", destination)
    search_hits = call_tool(state, "locations_agent", "WebSearchAPI", f"Top attractions in {destination}", 5)
    transit_hint = call_tool(state, "locations_agent", "MapsAPI", "city_center", destination)
    review_hits = call_tool(state, "locations_agent", "ReviewsAPI", f"Tourist attractions {destination}", 5)
    optimization_hints = state.get("optimization_hints", {})

    system = role_prompt("Locations Agent")
    user = (
        "Use TouristAttractionAPI to build a shortlist.\n"
        "Return JSON with keys: top_attractions, neighborhood_strategy, daily_intensity, estimated_total_sgd.\n"
        f"Requirements: {json.dumps(req)}\n"
        f"Feedback: {state.get('feedback', '')}\n"
        f"Optimization hints: {json.dumps(optimization_hints)}\n"
        f"Prior team messages: {recent_conversation(state)}\n"
        f"TouristAttractionAPI: {json.dumps(attractions)}\n"
        f"WebSearchAPI: {json.dumps(search_hits)}\n"
        f"MapsAPI: {json.dumps(transit_hint)}\n"
        f"ReviewsAPI: {json.dumps(review_hits)}"
    )
    plan = invoke_json(system, user)
    if not plan:
        log_agent("locations_agent", "LLM output invalid JSON, using deterministic fallback")
        cheaper = optimization_hints.get("target_reduction_sgd", 0) > 0
        top = sorted(attractions[:3], key=lambda x: x.get("ticket_sgd", 0))
        selected = top[:2] if cheaper else top[:3]
        plan = {
            "top_attractions": selected,
            "neighborhood_strategy": "Cluster activities by nearby areas.",
            "daily_intensity": "2 major activities per day." if cheaper else "2-3 major activities per day.",
            "estimated_total_sgd": sum(item["ticket_sgd"] for item in selected),
        }

    state["locations_plan"] = plan
    log_agent(
        "locations_agent",
        f"Selected attractions count: {len(plan.get('top_attractions', []))}",
    )
    state.setdefault("conversation", []).append(("locations_agent", plan))
    return state
