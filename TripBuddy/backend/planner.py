import json
import time
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
from metrics import AGENT_LATENCY


def _compute_end_date(start_date: str, days: int) -> str:
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = start + timedelta(days=days - 1)
    return end.isoformat()


def build_initial_state(requirements: Dict[str, Any]) -> Dict[str, Any]:
    req = {
        "days": int(requirements["days"]),
        "budget_sgd": float(requirements["budget_sgd"]),
        "location_preference": str(requirements["country"]).strip(),
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
        state.setdefault("conversation", []).append(("human_feedback", state["feedback"]))

    max_rounds = int(state.get("max_rounds", 3))
    aborted = False
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
            step_started_at = time.perf_counter()
            state = fn(state)
            AGENT_LATENCY.labels(agent_name=name).observe(time.perf_counter() - step_started_at)
            if abort_requested():
                aborted = True
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
        break

    state["_abort_run"] = False
    if aborted:
        yield {
            "type": "aborted",
            "round": int(state.get("round_number", 0)),
            "message": "Planning stopped by user.",
            "final_report": _normalize_json(state.get("final_report", state.get("report", {}))),
            "report_markdown": state.get("report_markdown", ""),
            "budget_plan": _normalize_json(state.get("budget_plan", {})),
        }
        return state

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
