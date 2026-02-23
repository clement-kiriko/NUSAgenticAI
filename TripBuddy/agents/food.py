import json
import os

import openai

from agents.orchestrator import call_tool, invoke_json, log_agent, recent_conversation
from prompts import role_prompt
from tools.food_finder import search_dining

_SEARCH_DINING_TOOL = {
    "type": "function",
    "function": {
        "name": "search_dining",
        "description": "Search for real nearby dining options given a location.",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "The location to search near, e.g. 'Orchard Road, Singapore'",
                },
                "radius_m": {
                    "type": "integer",
                    "description": "Search radius in metres (default 500)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max number of results to return (default 5)",
                },
            },
            "required": ["location"],
        },
    },
}


def _run_dining_tool_loop(state: dict, destination: str) -> list:
    """Two-step agentic loop mirroring the reference pattern.

    Step 1 – First LLM call: the model decides to invoke ``search_dining``.
    Step 2 – Execute the tool, then a second LLM call formats the raw results.
    Returns the list of live venue dicts produced by ``search_dining``.
    """
    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    model = os.getenv("OPENAI_MODEL", "gpt-4o")

    messages = [
        {
            "role": "system",
            "content": (
                "You are a travel dining assistant. "
                "Use the search_dining tool to find real dining options for the given location."
            ),
        },
        {"role": "user", "content": f"Find dining options near {destination}."},
    ]

    # First call — let the model decide to use the tool
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        tools=[_SEARCH_DINING_TOOL],
        tool_choice="auto",
    )
    message = response.choices[0].message

    live_results: list = []
    if message.tool_calls:
        messages.append(message)

        for tool_call in message.tool_calls:
            args = json.loads(tool_call.function.arguments)
            log_agent("food_agent", f"[Tool Call] search_dining({args})")
            # Register the call in framework state for auditability
            state.setdefault("tool_calls", []).append(
                {"agent": "food_agent", "tool": "search_dining", "args": args}
            )
            results = search_dining(**args)
            live_results = results
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(results),
                }
            )

        # Second call — model acknowledges / summarises the tool results
        response = client.chat.completions.create(
            model=model,
            messages=messages,
        )
        log_agent("food_agent", f"Dining tool loop complete: {response.choices[0].message.content[:120]}")

    return live_results


def food_agent(state: dict) -> dict:
    log_agent("food_agent", "Generating meal strategy from FoodAPI and team context")
    req = state["user_requirements"]
    destination = req["location_preference"]

    # Existing framework tool calls (mock data + web/review hits)
    options = call_tool(state, "food_agent", "FoodAPI", destination)
    search_hits = call_tool(state, "food_agent", "WebSearchAPI", f"Best food areas in {destination}", 5)
    review_hits = call_tool(state, "food_agent", "ReviewsAPI", f"Restaurants in {destination}", 5)

    # Agentic two-step loop: model calls search_dining, results fed back to LLM
    live_options = _run_dining_tool_loop(state, destination)
    log_agent("food_agent", f"search_dining returned {len(live_options)} live venue(s)")

    optimization_hints = state.get("optimization_hints", {})

    system = role_prompt("Food Agent")
    user = (
        "Use all provided food data to suggest a daily meal strategy.\n"
        "Return JSON with keys: meal_plan, dietary_notes, top_food_spots, estimated_total_sgd.\n"
        f"Requirements: {json.dumps(req)}\n"
        f"Feedback: {state.get('feedback', '')}\n"
        f"Optimization hints: {json.dumps(optimization_hints)}\n"
        f"Prior team messages: {recent_conversation(state)}\n"
        f"FoodAPI (mock): {json.dumps(options)}\n"
        f"Live dining results (search_dining): {json.dumps(live_options)}\n"
        f"WebSearchAPI: {json.dumps(search_hits)}\n"
        f"ReviewsAPI: {json.dumps(review_hits)}"
    )
    plan = invoke_json(system, user)
    if not plan:
        log_agent("food_agent", "LLM output invalid JSON, using deterministic fallback")
        days = req["days"]
        cheaper = optimization_hints.get("target_reduction_sgd", 0) > 0
        meal_cost = options[0]["cost_per_meal_sgd"] * 2 + (
            options[0]["cost_per_meal_sgd"] if cheaper else options[1]["cost_per_meal_sgd"]
        )
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
