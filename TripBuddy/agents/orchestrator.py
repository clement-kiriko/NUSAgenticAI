import json
import os
from typing import Any, Dict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from prompts import role_prompt
from tools import (
    accomodation_api,
    flight_api,
    food_api,
    maps_api,
    reviews_api,
    tourist_attraction_api,
    weather_api,
    web_search_api,
)
from metrics import (
    AGENT_TOOL_CALLS,
    AGENT_LATENCY,
    token_counter_total,
    token_counter_prompt,
    token_counter_completion,
)
from utils import debug
from prometheus_client import Counter, Histogram


TOOL_REGISTRY = {
    "FlightAPI": flight_api,
    "WeatherAPI": weather_api,
    "TouristAttractionAPI": tourist_attraction_api,
    "FoodAPI": food_api,
    "AccomsAPI": accomodation_api,
    "WebSearchAPI": web_search_api,
    "MapsAPI": maps_api,
    "ReviewsAPI": reviews_api,
}

TOOL_PERMISSIONS = {
    "flight_agent": {"FlightAPI", "WeatherAPI"},
    "locations_agent": {"TouristAttractionAPI", "WebSearchAPI", "MapsAPI", "ReviewsAPI"},
    "food_agent": {"FoodAPI", "WebSearchAPI", "ReviewsAPI"},
    "accomodations_agent": {"AccomsAPI", "WebSearchAPI", "MapsAPI", "ReviewsAPI"},
    "budget_agent": set(),
}


def advisor_llm() -> ChatOpenAI:
    model = os.getenv("OPENAI_MODEL", "gpt-5")
    return ChatOpenAI(model=model, temperature=1)

def call_llm(llm, messages):
    import time
    from langchain.callbacks import get_openai_callback
    start = time.time()

    with get_openai_callback() as cb:
        response = llm.invoke(messages)

        duration = time.time() - start

        usage = response.get("usage", {})
        
        token_counter_prompt.labels(model=os.getenv("OPENAI_MODEL", "gpt-5")).inc(usage["prompt_tokens"])
        token_counter_completion.labels(model=os.getenv("OPENAI_MODEL", "gpt-5")).inc(usage["completion_tokens"])
        token_counter_total.labels(model=os.getenv("OPENAI_MODEL", "gpt-5")).inc(usage["total_tokens"])

        return response

def invoke_json(system_prompt: str, user_prompt: str) -> Dict[str, Any]:
    try:
        debug(f"System prompt preview: {system_prompt[:220]}", prefix="LLM")
        debug(f"User prompt preview: {user_prompt[:360]}", prefix="LLM")
        raw = advisor_llm().invoke(
            [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
        ).content
        if isinstance(raw, list):
            raw = "".join(str(part) for part in raw)
        debug(f"Raw model response: {str(raw)[:420]}", prefix="LLM")
        return json.loads(raw)
    except Exception as exc:
        debug(f"JSON parse or invoke failure: {exc}", prefix="LLM")
        return {}


def call_tool(state: dict, agent_name: str, tool_name: str, *args, **kwargs):
    allowed = TOOL_PERMISSIONS.get(agent_name, set())
    AGENT_TOOL_CALLS.labels(tool_name=tool_name).inc()
    if tool_name not in allowed:
        raise PermissionError(f"{agent_name} is not allowed to call {tool_name}")
    result = TOOL_REGISTRY[tool_name](*args, **kwargs)
    debug(f"{agent_name} -> {tool_name} args={list(args)}", prefix="TOOL")
    debug(f"{tool_name} result preview: {str(result)[:260]}", prefix="TOOL")
    state.setdefault("tool_calls", []).append(
        {"agent": agent_name, "tool": tool_name, "args": list(args)}
    )
    return result


def recent_conversation(state: dict, limit: int = 8) -> str:
    history = state.get("conversation", [])
    tail = history[-limit:]
    return json.dumps([{"speaker": s, "message": m} for s, m in tail], ensure_ascii=True)


def log_agent(agent_name: str, message: str):
    print(f"[{agent_name}] {message}")


def orchestrator_agent(state: dict) -> dict:
    next_round = int(state.get("round_number", 0)) + 1
    state["round_number"] = next_round
    log_agent("orchestrator", f"Starting round {next_round}")
    state.setdefault("conversation", []).append(
        (
            "orchestrator",
            (
                f"Round {next_round} round-robin sequence: "
                "Flight -> Locations -> Food -> Accomodations -> Budget."
            ),
        )
    )
    return state


def consolidation_agent(state: dict) -> dict:
    req = state["user_requirements"]
    log_agent("consolidation", "Combining specialist outputs into unified report")
    system = role_prompt("Orchestrator / Consolidation Agent")
    user = (
        "Combine all specialist outputs into one user-facing report.\n"
        "Return JSON with keys: overview, recommendations, budget_summary, risks, next_iteration_focus.\n"
        f"Requirements: {json.dumps(req)}\n"
        f"Flight: {json.dumps(state.get('flight_plan', {}))}\n"
        f"Locations: {json.dumps(state.get('locations_plan', {}))}\n"
        f"Food: {json.dumps(state.get('food_plan', {}))}\n"
        f"Accomodations: {json.dumps(state.get('accomodations_plan', {}))}\n"
        f"Budget: {json.dumps(state.get('budget_plan', {}))}\n"
        f"Feedback: {state.get('feedback', '')}\n"
        f"Conversation: {recent_conversation(state, limit=12)}"
    )
    report = invoke_json(system, user)
    if not report:
        log_agent("consolidation", "LLM consolidation fallback activated")
        report = {
            "overview": f"{req['days']}-day plan for {req['location_preference']}.",
            "recommendations": {
                "flight": state.get("flight_plan", {}),
                "locations": state.get("locations_plan", {}),
                "food": state.get("food_plan", {}),
                "accomodations": state.get("accomodations_plan", {}),
            },
            "budget_summary": state.get("budget_plan", {}),
            "risks": ["Prices may fluctuate based on travel dates."],
            "next_iteration_focus": "Refine based on your feedback.",
        }

    state["report"] = report
    log_agent("consolidation", f"Report ready with keys: {list(report.keys())}")
    state.setdefault("conversation", []).append(("consolidation", report))
    return state
