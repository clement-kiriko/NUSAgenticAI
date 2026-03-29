import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, Generator

from agents import (
    accomodations_agent,
    budget_agent,
    consolidation_agent,
    flight_agent,
    food_agent,
    locations_agent,
    orchestrator_agent,
)
from monitoring import timed_agent_call

logger = logging.getLogger(__name__)

_CITY_UPDATE_PATTERNS = (
    re.compile(
        r"\b(?:change|set|update|switch)\s+(?:the\s+)?city\s+(?:to\s+)?(?P<city>[A-Za-z][A-Za-z\s.'-]{1,60})",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bcity\s*(?::|=|to)\s*(?P<city>[A-Za-z][A-Za-z\s.'-]{1,60})",
        re.IGNORECASE,
    ),
)
_DESTINATION_PHRASE_PATTERNS = (
    re.compile(
        r"\b(?:go to|visit|travel to|head to|prefer|instead of|rather than)\s+(?P<cities>[A-Za-z][A-Za-z\s.'-]*(?:\s*(?:,|/|and|or)\s*[A-Za-z][A-Za-z\s.'-]*)*)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:not\s+[A-Za-z][A-Za-z\s.'-]*,\s*)?(?:i want to go to|i want to visit|i'd like to visit|i would like to visit)\s+(?P<cities>[A-Za-z][A-Za-z\s.'-]*(?:\s*(?:,|/|and|or)\s*[A-Za-z][A-Za-z\s.'-]*)*)",
        re.IGNORECASE,
    ),
)
_CITY_SPLIT_PATTERN = re.compile(r"\s*(?:,|/|\band\b|\bor\b)\s*", re.IGNORECASE)
_NOISE_WORDS = {
    "please",
    "trip",
    "plan",
    "my",
    "the",
    "a",
    "an",
    "for",
    "now",
    "thanks",
    "thank you",
    "maybe",
    "can we do",
    "can we visit",
}
_TRAILING_CITY_PHRASES = (
    " instead",
    " now",
    " please",
    " this time",
    " for this trip",
    " only",
)
_COUNTRY_HINTS = {
    "indonesia",
    "japan",
    "thailand",
    "singapore",
    "malaysia",
    "vietnam",
    "korea",
    "south korea",
    "taiwan",
    "china",
}


def _build_location_preference(country: str, city: str = "") -> str:
    cleaned_country = str(country).strip()
    cleaned_city = str(city).strip()
    if cleaned_city:
        return f"{cleaned_city}, {cleaned_country}" if cleaned_country else cleaned_city
    return cleaned_country


def _compute_end_date(start_date: str, days: int) -> str:
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = start + timedelta(days=days - 1)
    return end.isoformat()


def build_initial_state(requirements: Dict[str, Any]) -> Dict[str, Any]:
    country = str(requirements["country"]).strip()
    city = str(requirements.get("city") or "").strip()
    requested_cities = [city] if city else []
    req = {
        "days": int(requirements["days"]),
        "budget_sgd": float(requirements["budget_sgd"]),
        "country": country,
        "city": city,
        "requested_cities": requested_cities,
        "location_preference": _build_location_preference(country, city),
        "start_date": str(requirements["start_date"]),
        "end_date": _compute_end_date(str(requirements["start_date"]), int(requirements["days"])),
        "dietary_restrictions": str(requirements.get("dietary_restrictions") or "none").strip() or "none",
    }
    return {
        "user_requirements": req,
        "feedback": "",
        "satisfied": False,
        "auto_rerun": False,
        "round_number": 0,
        "max_rounds": 3,
        "optimization_hints": {},
        "tool_calls": [],
        "conversation": [("human_intake", req)],
    }


def _clean_extracted_city(value: str) -> str:
    city = re.split(r"[,.!?\n\r]+", value, maxsplit=1)[0]
    return city.strip(" .,'\"")


def _normalize_city_token(value: str) -> str:
    cleaned = value.strip(" .,'\"")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    lowered = cleaned.casefold()
    for suffix in _TRAILING_CITY_PHRASES:
        if lowered.endswith(suffix):
            cleaned = cleaned[: -len(suffix)].strip(" .,'\"")
            lowered = cleaned.casefold()
    return cleaned.title()


def _dedupe_cities(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = _normalize_city_token(value)
        key = normalized.casefold()
        if not normalized or key in seen or key in _COUNTRY_HINTS:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def _extract_city_list(value: str) -> list[str]:
    cleaned = value.strip()
    if not cleaned:
        return []
    pieces = _CITY_SPLIT_PATTERN.split(cleaned)
    filtered = [piece for piece in pieces if piece and piece.casefold() not in _NOISE_WORDS]
    return _dedupe_cities(filtered)


def _extract_destination_updates_with_rules(feedback: str) -> Dict[str, Any]:
    for pattern in _CITY_UPDATE_PATTERNS:
        match = pattern.search(feedback)
        if match:
            cities = _extract_city_list(match.group("city"))
            if cities:
                return {"cities": cities}

    for pattern in _DESTINATION_PHRASE_PATTERNS:
        match = pattern.search(feedback)
        if match:
            cities = _extract_city_list(match.group("cities"))
            if cities:
                return {"cities": cities}

    return {}


def _extract_destination_updates_with_llm(state: Dict[str, Any], feedback: str) -> Dict[str, Any]:
    try:
        from agents.orchestrator import invoke_json
        from tools.security.guardrail import detect_prompt_injection
    except Exception:
        return {}

    if detect_prompt_injection(feedback):
        return {}

    req = state.get("user_requirements", {})
    system = (
        "Extract destination updates from the user's travel-planning feedback. "
        "Return JSON only with keys: cities (array of strings), country (string), clear_city (boolean). "
        "If no destination update is requested, return {\"cities\": [], \"country\": \"\", \"clear_city\": false}. "
        "Do not invent cities. Preserve only explicit user intent."
    )
    user = (
        f"Current requirements: {json.dumps(req, ensure_ascii=True)}\n"
        f"Feedback: {feedback}\n"
        "Examples:\n"
        "- 'change city to jakarta' => {\"cities\": [\"Jakarta\"], \"country\": \"\", \"clear_city\": false}\n"
        "- 'not bali, i want to go to jakarta or bandung' => {\"cities\": [\"Jakarta\", \"Bandung\"], \"country\": \"\", \"clear_city\": false}\n"
        "- 'just indonesia, no specific city' => {\"cities\": [], \"country\": \"Indonesia\", \"clear_city\": true}"
    )
    parsed = invoke_json(state, system, user)
    if not isinstance(parsed, dict):
        return {}

    cities = parsed.get("cities")
    country = str(parsed.get("country") or "").strip()
    clear_city = bool(parsed.get("clear_city", False))
    if not isinstance(cities, list):
        cities = []
    return {
        "cities": _dedupe_cities([str(city) for city in cities]),
        "country": country,
        "clear_city": clear_city,
    }


def _extract_destination_updates(state: Dict[str, Any], feedback: str) -> Dict[str, Any]:
    llm_updates = _extract_destination_updates_with_llm(state, feedback)
    if llm_updates.get("cities") or llm_updates.get("country") or llm_updates.get("clear_city"):
        return llm_updates
    return _extract_destination_updates_with_rules(feedback)


def _apply_feedback_updates(state: Dict[str, Any], feedback: str) -> None:
    cleaned_feedback = str(feedback or "").strip()
    if not cleaned_feedback:
        return

    req = state.get("user_requirements")
    if not isinstance(req, dict):
        return

    updates = _extract_destination_updates(state, cleaned_feedback)
    cities = _dedupe_cities([str(city) for city in updates.get("cities", [])])
    country = str(updates.get("country") or "").strip()
    clear_city = bool(updates.get("clear_city", False))

    if country:
        req["country"] = country

    if cities:
        req["city"] = cities[0]
        req["requested_cities"] = cities
    elif clear_city:
        req["city"] = ""
        req["requested_cities"] = []
    else:
        return

    req["location_preference"] = _build_location_preference(req.get("country", ""), req.get("city", ""))
    logger.info(
        "Planner feedback updated destination city=%s requested_cities=%s location_preference=%s",
        req.get("city", ""),
        req.get("requested_cities", []),
        req["location_preference"],
    )


def _run_one_round(state: Dict[str, Any]) -> Dict[str, Any]:
    state = orchestrator_agent(state)
    state = flight_agent(state)
    state = locations_agent(state)
    state = food_agent(state)
    state = accomodations_agent(state)
    state = budget_agent(state)
    state = consolidation_agent(state)
    return state


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return len(value) > 0
    return True


def _missing_critical_fields(state: Dict[str, Any]) -> list[str]:
    missing: list[str] = []
    flight = state.get("flight_plan", {})
    locations = state.get("locations_plan", {})
    food = state.get("food_plan", {})
    accomodations = state.get("accomodations_plan", {})
    budget = state.get("budget_plan", {})
    report = state.get("report", {})

    if not _has_value(flight.get("selected_option")):
        missing.append("flight.selected_option")
    if not _has_value(locations.get("top_attractions")):
        missing.append("locations.top_attractions")
    if not _has_value(food.get("meal_plan")):
        missing.append("food.meal_plan")
    if not _has_value(accomodations.get("selected_stay")):
        missing.append("accomodations.selected_stay")
    if "projected_total_sgd" not in budget:
        missing.append("budget.projected_total_sgd")
    if "within_budget" not in budget:
        missing.append("budget.within_budget")
    if not _has_value(report.get("overview")):
        missing.append("report.overview")
    if not _has_value(report.get("recommendations")):
        missing.append("report.recommendations")
    if not _has_value(report.get("budget_summary")):
        missing.append("report.budget_summary")

    return missing


def _should_auto_rerun(state: Dict[str, Any]) -> tuple[bool, list[str], bool]:
    within_budget = bool(state.get("budget_plan", {}).get("within_budget", False))
    missing_fields = _missing_critical_fields(state)
    round_number = int(state.get("round_number", 1))
    max_rounds = int(state.get("max_rounds", 3))
    should_retry = (round_number < max_rounds) and ((not within_budget) or bool(missing_fields))
    return should_retry, missing_fields, within_budget


def _normalize_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _normalize_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize_json(v) for v in value]
    return value


def report_to_markdown(report: Dict[str, Any]) -> str:
    lines: list[str] = ["# Trip Plan Report"]
    overview = report.get("overview")
    if overview:
        lines.append("")
        lines.append(f"## Overview\n{overview}")

    def render_section(title: str, value: Any, indent: int = 0) -> None:
        prefix = "  " * indent
        if isinstance(value, dict):
            for key, sub in value.items():
                safe_key = str(key).replace("_", " ").title()
                if isinstance(sub, (dict, list)):
                    lines.append(f"{prefix}- **{safe_key}**")
                    render_section(title, sub, indent + 1)
                else:
                    lines.append(f"{prefix}- **{safe_key}**: {sub}")
            return
        if isinstance(value, list):
            for item in value:
                if isinstance(item, (dict, list)):
                    lines.append(f"{prefix}-")
                    render_section(title, item, indent + 1)
                else:
                    lines.append(f"{prefix}- {item}")
            return
        lines.append(f"{prefix}- {value}")

    for key in ("recommendations", "budget_summary", "risks", "next_iteration_focus"):
        section = report.get(key)
        if section is None:
            continue
        lines.append("")
        lines.append(f"## {key.replace('_', ' ').title()}")
        render_section(key, section)

    return "\n".join(lines)


def run_planner_stream(
    state: Dict[str, Any],
    feedback: str = "",
) -> Generator[Dict[str, Any], None, Dict[str, Any]]:
    def abort_requested() -> bool:
        return bool(state.get("_abort_run", False))

    if feedback.strip():
        state["feedback"] = feedback.strip()
        _apply_feedback_updates(state, state["feedback"])
        state.setdefault("conversation", []).append(("human_feedback", state["feedback"]))
        logger.info("Planner feedback received round=%s feedback=%s", state.get("round_number", 0), feedback.strip())

    max_rounds = int(state.get("max_rounds", 3))
    aborted = False
    logger.info(
        "Planner run started destination=%s start_date=%s end_date=%s max_rounds=%s",
        state.get("user_requirements", {}).get("location_preference"),
        state.get("user_requirements", {}).get("start_date"),
        state.get("user_requirements", {}).get("end_date"),
        max_rounds,
    )
    step_start_msg = {
        "orchestrator": "Setting planning strategy for this round.",
        "flight": "Checking flights and weather conditions.",
        "locations": "Exploring attractions and daily activity flow.",
        "food": "Looking for food options and dietary-friendly picks.",
        "accomodations": "Comparing accommodation options and areas.",
        "budget": "Calculating total spend and budget fit.",
        "consolidation": "Merging everything into one readable plan.",
    }
    step_end_msg = {
        "orchestrator": "Planning strategy ready.",
        "flight": "Flight recommendations completed.",
        "locations": "Attraction shortlist completed.",
        "food": "Food plan completed.",
        "accomodations": "Accommodation plan completed.",
        "budget": "Budget check completed.",
        "consolidation": "Final report draft completed.",
    }
    while int(state.get("round_number", 0)) < max_rounds:
        if abort_requested():
            aborted = True
            break

        next_round = int(state.get("round_number", 0)) + 1
        logger.info("Planner round started round=%s max_rounds=%s", next_round, max_rounds)
        yield {"type": "round_started", "round": next_round, "max_rounds": max_rounds}

        for name, fn in (
            ("orchestrator", orchestrator_agent),
            ("flight", flight_agent),
            ("locations", locations_agent),
            ("food", food_agent),
            ("accomodations", accomodations_agent),
            ("budget", budget_agent),
            ("consolidation", consolidation_agent),
        ):
            if abort_requested():
                aborted = True
                break
            yield {
                "type": "step_started",
                "step": name,
                "round": next_round,
                "message": step_start_msg.get(name, f"Running {name}"),
            }
            logger.info("Planner step started round=%s step=%s", next_round, name)
            try:
                state = timed_agent_call(name, fn, state)
            except Exception:
                logger.exception("Planner step failed round=%s step=%s", next_round, name)
                raise
            if abort_requested():
                aborted = True
            logger.info("Planner step completed round=%s step=%s", next_round, name)
            yield {
                "type": "step_completed",
                "step": name,
                "round": next_round,
                "message": step_end_msg.get(name, f"Completed {name}"),
            }
            if aborted:
                break

        if aborted:
            break

        report = state.get("report", {})
        normalized = _normalize_json(report)
        markdown = report_to_markdown(normalized)
        yield {
            "type": "report_ready",
            "round": int(state.get("round_number", next_round)),
            "report": normalized,
            "report_markdown": markdown,
            "budget_plan": _normalize_json(state.get("budget_plan", {})),
        }

        should_retry, missing_fields, within_budget = _should_auto_rerun(state)
        if should_retry:
            state["auto_rerun"] = True
            state["satisfied"] = False
            reasons: list[str] = []
            if not within_budget:
                reasons.append("Current plan exceeds budget.")
            if missing_fields:
                reasons.append("Some required plan fields are incomplete.")
            state["feedback"] = " ".join(reasons) + (
                " Revise using optimization_hints and provide complete outputs for all specialists."
            )
            state.setdefault("conversation", []).append(("system_auto_feedback", state["feedback"]))
            logger.warning(
                "Planner auto-rerun triggered round=%s within_budget=%s missing_fields=%s reason=%s",
                int(state.get("round_number", next_round)),
                within_budget,
                missing_fields,
                state["feedback"],
            )
            yield {
                "type": "auto_rerun",
                "round": int(state.get("round_number", next_round)),
                "max_rounds": max_rounds,
                "reason": state["feedback"],
                "missing_fields": missing_fields,
                "within_budget": within_budget,
            }
            continue

        state["auto_rerun"] = False
        state["final_report"] = normalized
        state["report_markdown"] = markdown
        logger.info(
            "Planner run converged round=%s within_budget=%s report_keys=%s",
            int(state.get("round_number", next_round)),
            within_budget,
            sorted(normalized.keys()) if isinstance(normalized, dict) else [],
        )
        break

    state["_abort_run"] = False
    if aborted:
        logger.warning("Planner run aborted round=%s", int(state.get("round_number", 0)))
        yield {
            "type": "aborted",
            "round": int(state.get("round_number", 0)),
            "message": "Planning stopped by user.",
            "final_report": _normalize_json(state.get("final_report", state.get("report", {}))),
            "report_markdown": state.get("report_markdown", ""),
            "budget_plan": _normalize_json(state.get("budget_plan", {})),
        }
        return state

    logger.info("Planner run completed round=%s", int(state.get("round_number", 0)))
    yield {
        "type": "completed",
        "round": int(state.get("round_number", 0)),
        "max_rounds": max_rounds,
        "final_report": _normalize_json(state.get("final_report", state.get("report", {}))),
        "report_markdown": state.get("report_markdown", ""),
        "budget_plan": _normalize_json(state.get("budget_plan", {})),
    }
    return state


def run_planner_once(state: Dict[str, Any], feedback: str = "") -> Dict[str, Any]:
    for _ in run_planner_stream(state, feedback=feedback):
        pass
    return state


def as_sse_event(event_name: str, payload: Dict[str, Any]) -> str:
    return f"event: {event_name}\ndata: {json.dumps(payload, ensure_ascii=True)}\n\n"
