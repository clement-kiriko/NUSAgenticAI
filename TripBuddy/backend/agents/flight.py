import json

from agents.orchestrator import (
    call_tool_by_capability,
    discover_tools,
    invoke_json,
    log_agent,
    recent_conversation,
)
from prompts import role_prompt


def _emit_progress(state: dict, message: str) -> None:
    emit = state.get("_emit_event")
    if callable(emit):
        emit({"type": "agent_update", "step": "flight", "message": message})


def flight_agent(state: dict) -> dict:
    log_agent("flight_agent", "Reviewing requirements and flight/weather options")
    req = state["user_requirements"]
    destination = req["location_preference"]
    days = req["days"]
    _emit_progress(state, f"Checking trip dates ({req.get('start_date')} to {req.get('end_date')}) for {destination}.")

    catalog = discover_tools("flight_agent")
    log_agent("flight_agent", f"Discovered tools: {[tool['name'] for tool in catalog]}")
    _emit_progress(state, "Searching flight options.")
    options = call_tool_by_capability(state, "flight_agent", "flight_search", "Singapore", destination, days)
    _emit_progress(state, "Querying destination weather.")
    weather = call_tool_by_capability(state, "flight_agent", "weather_current", destination)
    optimization_hints = state.get("optimization_hints", {})

    system = role_prompt("Flight Agent")
    user = (
        "Use FlightAPI and WeatherAPI results to recommend a flight strategy.\n"
        "Return JSON with keys: selected_option, rationale, weather_notes, estimated_total_sgd.\n"
        f"FlightAPI: {json.dumps(options)}\n"
        f"Requirements: {json.dumps(req)}\n"
        f"Feedback: {state.get('feedback', '')}\n"
        f"Optimization hints: {json.dumps(optimization_hints)}\n"
        f"Prior team messages: {recent_conversation(state)}\n"        
        f"WeatherAPI: {json.dumps(weather)}"
    )
    plan = invoke_json(system, user)
    if not plan:
        log_agent("flight_agent", "LLM output invalid JSON, using deterministic fallback")
        if options:
            selected = options[-1] if optimization_hints.get("target_reduction_sgd", 0) > 0 else options[0]
        else:
            selected = {"route": "No live flight options found", "price_sgd": 0}
        plan = {
            "selected_option": selected,
            "rationale": "Cost-optimized option based on current budget pressure.",
            "weather_notes": weather.get("forecast", "Weather data unavailable."),
            "estimated_total_sgd": selected.get("price_sgd", 0),
        }

    state["flight_plan"] = plan
    log_agent(
        "flight_agent",
        f"Proposed flight cost SGD: {plan.get('estimated_total_sgd', 'N/A')}",
    )
    state.setdefault("conversation", []).append(("flight_agent", plan))
    return state
