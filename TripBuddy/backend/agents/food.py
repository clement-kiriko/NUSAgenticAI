import json

from agents.orchestrator import (
    call_tool,
    call_tool_by_capability,
    discover_tools,
    invoke_json,
    llm_chat,
    log_agent,
    recent_conversation,
    tool_schema,
)
from prompts import role_prompt


def _emit_progress(state: dict, message: str) -> None:
    emit = state.get("_emit_event")
    if callable(emit):
        emit({"type": "agent_update", "step": "food", "message": message})


def _run_dining_tool_loop(state: dict, destination: str) -> list:
    """Two-step tool-use loop routed via LLM Router + Tool Gateway."""
    search_tool_name = "food_search_live"
    schema = tool_schema("food_agent", search_tool_name)
    messages = [
        {
            "role": "system",
            "content": (
                "You are a travel dining assistant. "
                "Use the food_search_live tool to find real dining options for the given location."
            ),
        },
        {"role": "user", "content": f"Find dining options near {destination}."},
    ]

    response = llm_chat(messages, task_type="tool_use", tools=[schema], tool_choice="auto")
    message = response.choices[0].message

    live_results: list = []
    if message.tool_calls:
        messages.append(message)
        for tool_call in message.tool_calls:
            args = json.loads(tool_call.function.arguments)
            log_agent("food_agent", f"[Tool Call] food_search_live({args})")
            results = call_tool(state, "food_agent", search_tool_name, **args)
            live_results = results
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(results),
                }
            )

        response = llm_chat(messages, task_type="tool_use")
        summary = response.choices[0].message.content or ""
        log_agent("food_agent", f"Dining tool loop complete: {str(summary)[:120]}")

    return live_results


def food_agent(state: dict) -> dict:
    log_agent("food_agent", "Generating meal strategy from food_catalog and team context")
    req = state["user_requirements"]
    destination = req["location_preference"]
    _emit_progress(state, f"Exploring food options and dietary fit in {destination}.")
    catalog = discover_tools("food_agent")
    log_agent("food_agent", f"Discovered tools: {[tool['name'] for tool in catalog]}")

    options = call_tool_by_capability(state, "food_agent", "food_catalog", destination)
    search_hits = call_tool_by_capability(state, "food_agent", "geo_search", f"Best food areas in {destination}", 5)
    review_hits = call_tool_by_capability(state, "food_agent", "place_signals", f"Restaurants in {destination}", 5)

    _emit_progress(state, "Looking up live dining spots nearby.")
    live_options = _run_dining_tool_loop(state, destination)
    log_agent("food_agent", f"food_search_live returned {len(live_options)} live venue(s)")

    optimization_hints = state.get("optimization_hints", {})
    _emit_progress(state, "Building a day-by-day meal strategy.")

    system = role_prompt("Food Agent")
    user = (
        "Use all provided food data to suggest a daily meal strategy.\n"
        "Return JSON with keys: meal_plan, dietary_notes, top_food_spots, estimated_total_sgd.\n"
        f"Requirements: {json.dumps(req)}\n"
        f"Feedback: {state.get('feedback', '')}\n"
        f"Optimization hints: {json.dumps(optimization_hints)}\n"
        f"Prior team messages: {recent_conversation(state)}\n"
        f"food_catalog: {json.dumps(options)}\n"
        f"food_search_live: {json.dumps(live_options)}\n"
        f"places_search: {json.dumps(search_hits)}\n"
        f"place_signals: {json.dumps(review_hits)}"
    )
    plan = invoke_json(system, user)
    if not plan:
        log_agent("food_agent", "LLM output invalid JSON, using deterministic fallback")
        days = req["days"]
        cheaper = optimization_hints.get("target_reduction_sgd", 0) > 0
        base_cost = options[0]["cost_per_meal_sgd"] if options else 12
        premium_cost = options[1]["cost_per_meal_sgd"] if len(options) > 1 else base_cost
        meal_cost = base_cost * 2 + (base_cost if cheaper else premium_cost)
        plan = {
            "meal_plan": (
                "Breakfast local, lunch hawker, dinner mostly hawker/local stalls."
                if cheaper
                else "Breakfast local, lunch hawker, dinner mix of local/international."
            ),
            "dietary_notes": "Check allergens and halal/vegetarian labels on each venue.",
            "top_food_spots": (live_options or options)[:3],
            "estimated_total_sgd": meal_cost * days,
        }

    state["food_plan"] = plan
    log_agent(
        "food_agent",
        f"Estimated food budget SGD: {plan.get('estimated_total_sgd', 'N/A')}",
    )
    state.setdefault("conversation", []).append(("food_agent", plan))
    return state
