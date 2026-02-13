import json

from agents.orchestrator import call_tool, invoke_json, log_agent, recent_conversation
from prompts import role_prompt


def flight_agent(state: dict) -> dict:
    log_agent("flight_agent", "Reviewing requirements and flight/weather options")
    req = state["user_requirements"]
    destination = req["location_preference"]
    days = req["days"]

    options = call_tool(state, "flight_agent", "FlightAPI", "Singapore", destination, days)
    weather = call_tool(state, "flight_agent", "WeatherAPI", destination)
    optimization_hints = state.get("optimization_hints", {})

    system = role_prompt("Flight Agent")
    user = (
        "Use FlightAPI and WeatherAPI results to recommend a flight strategy.\n"
        "Return JSON with keys: selected_option, rationale, weather_notes, estimated_total_sgd.\n"
        f"Requirements: {json.dumps(req)}\n"
        f"Feedback: {state.get('feedback', '')}\n"
        f"Optimization hints: {json.dumps(optimization_hints)}\n"
        f"Prior team messages: {recent_conversation(state)}\n"
        f"FlightAPI: {json.dumps(options)}\n"
        f"WeatherAPI: {json.dumps(weather)}"
    )
    plan = invoke_json(system, user)
    if not plan:
        log_agent("flight_agent", "LLM output invalid JSON, using deterministic fallback")
        selected = options[-1] if optimization_hints.get("target_reduction_sgd", 0) > 0 else options[0]
        plan = {
            "selected_option": selected,
            "rationale": "Cost-optimized option based on current budget pressure.",
            "weather_notes": weather["forecast"],
            "estimated_total_sgd": selected["price_sgd"],
        }

    state["flight_plan"] = plan
    log_agent(
        "flight_agent",
        f"Proposed flight cost SGD: {plan.get('estimated_total_sgd', 'N/A')}",
    )
    state.setdefault("conversation", []).append(("flight_agent", plan))
    return state
