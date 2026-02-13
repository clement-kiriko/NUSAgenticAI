import json

from agents.orchestrator import call_tool, invoke_json, log_agent, recent_conversation
from prompts import role_prompt


def food_agent(state: dict) -> dict:
    log_agent("food_agent", "Generating meal strategy from FoodAPI and team context")
    req = state["user_requirements"]
    destination = req["location_preference"]
    options = call_tool(state, "food_agent", "FoodAPI", destination)
    search_hits = call_tool(state, "food_agent", "WebSearchAPI", f"Best food areas in {destination}", 5)
    review_hits = call_tool(state, "food_agent", "ReviewsAPI", f"Restaurants in {destination}", 5)
    optimization_hints = state.get("optimization_hints", {})

    system = role_prompt("Food Agent")
    user = (
        "Use FoodAPI data to suggest daily meal strategy.\n"
        "Return JSON with keys: meal_plan, dietary_notes, top_food_spots, estimated_total_sgd.\n"
        f"Requirements: {json.dumps(req)}\n"
        f"Feedback: {state.get('feedback', '')}\n"
        f"Optimization hints: {json.dumps(optimization_hints)}\n"
        f"Prior team messages: {recent_conversation(state)}\n"
        f"FoodAPI: {json.dumps(options)}\n"
        f"WebSearchAPI: {json.dumps(search_hits)}\n"
        f"ReviewsAPI: {json.dumps(review_hits)}"
    )
    plan = invoke_json(system, user)
    if not plan:
        log_agent("food_agent", "LLM output invalid JSON, using deterministic fallback")
        days = req["days"]
        cheaper = optimization_hints.get("target_reduction_sgd", 0) > 0
        meal_cost = options[0]["cost_per_meal_sgd"] * 2 + (options[0]["cost_per_meal_sgd"] if cheaper else options[1]["cost_per_meal_sgd"])
        plan = {
            "meal_plan": (
                "Breakfast local, lunch hawker, dinner mostly hawker/local stalls."
                if cheaper
                else "Breakfast local, lunch hawker, dinner mix of local/international."
            ),
            "dietary_notes": "Check allergens and halal/vegetarian labels on each venue.",
            "top_food_spots": options[:3],
            "estimated_total_sgd": meal_cost * days,
        }

    state["food_plan"] = plan
    log_agent(
        "food_agent",
        f"Estimated food budget SGD: {plan.get('estimated_total_sgd', 'N/A')}",
    )
    state.setdefault("conversation", []).append(("food_agent", plan))
    return state
