import json
import re
from typing import Any, Dict, List, Tuple

from agents.orchestrator import call_tool, invoke_json, log_agent, recent_conversation
from prompts import role_prompt


def _normalize_name(value: str) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9\s-]", "", value)
    value = re.sub(r"\s+", " ", value)
    return value


def _confidence(supported_sources: int, total_sources: int) -> float:
    """Simple confidence heuristic: more independent sources -> higher confidence."""
    if total_sources <= 0:
        return 0.4
    ratio = supported_sources / total_sources
    # Keep within [0.45, 0.95] to avoid false certainty.
    return round(max(0.45, min(0.95, 0.45 + 0.55 * ratio)), 2)


def _seasonal_tips(weather_forecast: str) -> List[str]:
    forecast = (weather_forecast or "").lower()
    tips: List[str] = []
    if any(k in forecast for k in ["shower", "rain", "storm"]):
        tips.extend(
            [
                "Keep 1-2 indoor attractions as backups in case of rain.",
                "Plan outdoor-heavy days earlier (morning) and leave evenings flexible.",
            ]
        )
    if any(k in forecast for k in ["hot", "warm", "humid"]):
        tips.extend(
            [
                "Add air-conditioned stops (museums, malls) between outdoor activities.",
                "Hydrate and avoid the harshest midday heat for long walks.",
            ]
        )
    if not tips:
        tips.append("Balance indoor and outdoor activities to stay flexible.")
    return tips


def _score_attraction(
    attraction: Dict[str, Any],
    req: Dict[str, Any],
    weather: Dict[str, Any],
    support: Dict[str, bool],
) -> Tuple[float, Dict[str, Any]]:
    """Deterministic scoring with transparent criteria."""
    ticket = float(attraction.get("ticket_sgd", 0) or 0)
    budget = float(req.get("budget_sgd", 0) or 0)

    # Price score: cheaper is better; normalize against per-day budget.
    per_day = budget / max(int(req.get("days", 1) or 1), 1)
    price_score = 1.0
    if per_day > 0:
        price_score = max(0.0, min(1.0, 1 - (ticket / max(per_day * 0.25, 1))))

    # Weather fit: if rain, prefer indoor-ish categories.
    forecast = (weather.get("forecast") or "").lower()
    atype = (attraction.get("type") or "").lower()
    indoor_bias = 0.0
    if any(k in forecast for k in ["shower", "rain", "storm"]):
        if any(k in atype for k in ["museum", "culture", "shopping", "indoor"]):
            indoor_bias = 1.0
        elif any(k in atype for k in ["scenic", "nature", "outdoor"]):
            indoor_bias = 0.4
        else:
            indoor_bias = 0.6
    else:
        indoor_bias = 0.7

    # Support score: cross-check across sources.
    supported_sources = sum(1 for v in support.values() if v)
    support_score = supported_sources / max(len(support), 1)

    total = round(0.45 * price_score + 0.25 * indoor_bias + 0.30 * support_score, 3)
    breakdown = {
        "price_score": round(price_score, 2),
        "weather_fit_score": round(indoor_bias, 2),
        "support_score": round(support_score, 2),
        "supported_by": [k for k, v in support.items() if v],
        "ticket_sgd": ticket,
    }
    return total, breakdown


def locations_agent(state: dict) -> dict:
    log_agent("locations_agent", "Building attraction shortlist from location preference")
    req = state["user_requirements"]
    destination = req["location_preference"]

    # Multi-source retrieval
    attractions = call_tool(state, "locations_agent", "TouristAttractionAPI", destination)
    weather = call_tool(state, "locations_agent", "WeatherAPI", destination)
    search_hits = call_tool(
        state, "locations_agent", "WebSearchAPI", f"Top attractions in {destination}", 5
    )
    transit_hint = call_tool(state, "locations_agent", "MapsAPI", "city_center", destination)
    review_hits = call_tool(
        state, "locations_agent", "ReviewsAPI", f"Tourist attractions {destination}", 5
    )
    optimization_hints = state.get("optimization_hints", {})

    # Cross-check signals for confidence scoring.
    search_names = {_normalize_name(row.get("name", "")) for row in (search_hits or [])}
    review_names = {_normalize_name(row.get("place", "")) for row in (review_hits or [])}

    scored: List[Dict[str, Any]] = []
    for item in attractions or []:
        name = item.get("name", "")
        norm = _normalize_name(name)
        support = {
            "TouristAttractionAPI": bool(norm),
            "WebSearchAPI": norm in search_names,
            "ReviewsAPI": norm in review_names,
        }
        score, breakdown = _score_attraction(item, req, weather, support)
        scored.append(
            {
                **item,
                "score": round(score, 2),
                "confidence": _confidence(sum(1 for v in support.values() if v), len(support)),
                "score_breakdown": breakdown,
                "why": (
                    "Ranked using transparent scoring across price, weather fit, and cross-source support. "
                    "Confidence increases when multiple sources agree."
                ),
            }
        )

    # Fairness/bias-aware behavior: do not up-rank sponsored-only results.
    # We treat WebSearchAPI hits as unverified hints unless they align with other sources.
    scored.sort(key=lambda x: (x.get("score", 0), x.get("confidence", 0)), reverse=True)

    system = role_prompt("Locations Agent")
    user = (
        "Build a shortlist of attractions and an activity strategy for the trip.\n"
        "Return JSON with keys: top_attractions, neighborhood_strategy, daily_intensity, estimated_total_sgd, "
        "confidence_notes, seasonal_tips, safety_notes.\n"
        "Fairness rule: do not recommend items solely because they look sponsored; prioritize transparent, "
        "criteria-based ranking.\n"
        f"Requirements: {json.dumps(req)}\n"
        f"Feedback: {state.get('feedback', '')}\n"
        f"Optimization hints: {json.dumps(optimization_hints)}\n"
        f"Prior team messages: {recent_conversation(state)}\n"
        f"WeatherAPI: {json.dumps(weather)}\n"
        f"TouristAttractionAPI: {json.dumps(scored)}\n"
        f"WebSearchAPI: {json.dumps(search_hits)}\n"
        f"MapsAPI: {json.dumps(transit_hint)}\n"
        f"ReviewsAPI: {json.dumps(review_hits)}"
    )
    plan = invoke_json(system, user)

    if not plan:
        log_agent("locations_agent", "LLM output invalid JSON, using deterministic fallback")
        cheaper = optimization_hints.get("target_reduction_sgd", 0) > 0
        # Deterministic selection uses scored list, preferring high score + confidence.
        base_pick = scored[: 2 if cheaper else 3] if scored else (attractions or [])[:3]
        selected = base_pick
        plan = {
            "top_attractions": selected,
            "neighborhood_strategy": "Cluster activities by nearby areas.",
            "daily_intensity": "2 major activities per day." if cheaper else "2-3 major activities per day.",
            "estimated_total_sgd": round(
                sum(float(item.get("ticket_sgd", 0) or 0) for item in selected), 2
            ),
            "confidence_notes": (
                "Confidence is based on agreement across TouristAttractionAPI, WebSearchAPI, and ReviewsAPI."
            ),
            "seasonal_tips": _seasonal_tips((weather or {}).get("forecast", "")),
            "safety_notes": [
                "Avoid sharing sensitive personal data in the chat.",
                "Check local advisories and stay alert in crowded areas.",
            ],
        }

    # Ensure the plan includes fields even when LLM returns valid JSON but omits them.
    plan.setdefault("seasonal_tips", _seasonal_tips((weather or {}).get("forecast", "")))
    plan.setdefault(
        "confidence_notes",
        "Confidence reflects cross-source validation and is conservative when only one source supports an item.",
    )
    plan.setdefault(
        "safety_notes",
        [
            "Follow official local advisories and avoid unsafe areas at night.",
            "Keep emergency contacts and travel insurance details accessible.",
        ],
    )

    state["locations_plan"] = plan
    log_agent("locations_agent", f"Selected attractions count: {len(plan.get('top_attractions', []))}")
    state.setdefault("conversation", []).append(("locations_agent", plan))
    return state