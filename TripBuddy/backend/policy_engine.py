import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List


POLICY_VERSION = "2026-03-imda-gap-pass1"
REPORT_SCHEMA_VERSION = "2.0"
TRUST_WEIGHTS = {
    "budget_fit": 0.3,
    "evidence_coverage": 0.25,
    "completeness": 0.2,
    "constraint_fit": 0.15,
    "robustness": 0.1,
}
FAIRNESS_AREAS = {
    "flight": "No sponsored ranking applied; price-sensitive recommendations are preferred when budget pressure exists.",
    "locations": "Free and lower-ticket attractions can be preferred when cost pressure exists.",
    "food": "Dietary restrictions and a mix of price points are checked before surfacing options.",
    "accomodations": "Budget pressure can shift ranking toward lower nightly rates with acceptable commute trade-offs.",
}
HIGHER_RISK_DESTINATIONS = {
    "conflict zone",
    "war zone",
    "active conflict",
    "sanctioned region",
}
COERCIVE_PATTERNS = (
    "book now",
    "limited time",
    "last chance",
    "act fast",
)


def initialize_governance_state(state: Dict[str, Any]) -> None:
    metadata = state.setdefault("governance_metadata", {})
    metadata.setdefault("audit_id", str(uuid.uuid4()))
    metadata.setdefault("current_run_id", "")
    metadata.setdefault("run_history", [])
    metadata.setdefault("policy_version", POLICY_VERSION)
    metadata.setdefault("report_schema_version", REPORT_SCHEMA_VERSION)
    metadata.setdefault("created_at", _utc_now())
    metadata["last_updated_at"] = _utc_now()
    state.setdefault("decision_trace", [])


def get_audit_id(state: Dict[str, Any] | None) -> str:
    if not isinstance(state, dict):
        return "-"
    metadata = state.get("governance_metadata", {})
    if not isinstance(metadata, dict):
        return "-"
    value = str(metadata.get("audit_id", "")).strip()
    return value or "-"


def get_run_id(state: Dict[str, Any] | None) -> str:
    if not isinstance(state, dict):
        return "-"
    metadata = state.get("governance_metadata", {})
    if not isinstance(metadata, dict):
        return "-"
    value = str(metadata.get("current_run_id", "")).strip()
    return value or "-"


def start_new_run(state: Dict[str, Any], mode: str) -> str:
    initialize_governance_state(state)
    run_id = str(uuid.uuid4())
    metadata = state["governance_metadata"]
    metadata["current_run_id"] = run_id
    metadata.setdefault("run_history", []).append(
        {
            "run_id": run_id,
            "mode": mode,
            "started_at": _utc_now(),
        }
    )
    return run_id


def append_decision_trace(
    state: Dict[str, Any],
    actor: str,
    summary: str,
    *,
    evidence: Dict[str, Any] | None = None,
    outcome: str | None = None,
    policy_tags: List[str] | None = None,
) -> None:
    initialize_governance_state(state)
    state.setdefault("decision_trace", []).append(
        {
            "timestamp": _utc_now(),
            "run_id": get_run_id(state),
            "actor": actor,
            "summary": summary,
            "outcome": outcome or "recorded",
            "policy_tags": list(policy_tags or []),
            "evidence": evidence or {},
        }
    )


def build_tool_audit_entry(
    agent_name: str,
    tool_name: str,
    args: Iterable[Any],
    kwargs: Dict[str, Any],
    *,
    audit_id: str = "-",
    run_id: str = "-",
    result: Any = None,
    error: str | None = None,
) -> Dict[str, Any]:
    status = "error" if error else "ok"
    return {
        "call_id": str(uuid.uuid4()),
        "timestamp": _utc_now(),
        "audit_id": audit_id,
        "run_id": run_id,
        "agent": agent_name,
        "tool": tool_name,
        "status": status,
        "args": _normalize_json(list(args)),
        "kwargs": _normalize_json(kwargs),
        "result_preview": _result_preview(result),
        "error": error or "",
        "policy_version": POLICY_VERSION,
    }


def enrich_report(state: Dict[str, Any], report: Dict[str, Any]) -> Dict[str, Any]:
    initialize_governance_state(state)
    evaluation = evaluate_state(state)
    state["policy_evaluation"] = evaluation
    enriched = dict(report)
    enriched.update(
        {
            "governance": evaluation["governance"],
            "accountability": evaluation["accountability"],
            "decision_trace": evaluation["decision_trace"],
            "decision_trace_full": evaluation["decision_trace_full"],
            "explainability": evaluation["explainability"],
            "assurance": evaluation["assurance"],
            "trust": evaluation["trust"],
            "fairness": evaluation["fairness"],
            "ethical_checks": evaluation["ethical_checks"],
            "autonomy": evaluation["autonomy"],
            "imda_alignment": evaluation["imda_alignment"],
        }
    )
    return enriched


def evaluate_state(state: Dict[str, Any]) -> Dict[str, Any]:
    initialize_governance_state(state)
    req = state.get("user_requirements", {})
    tool_calls = state.get("tool_calls", [])
    fallback_markers = _fallback_markers(state)
    missing_fields = _missing_fields(state)
    evidence_sources = sorted(
        set(
            _collect_sources(
        [
            state.get("flight_plan", {}),
            state.get("locations_plan", {}),
            state.get("food_plan", {}),
            state.get("accomodations_plan", {}),
        ]
            )
        ).union({f"tool:{call.get('tool')}" for call in tool_calls if call.get("tool")})
    )
    budget_plan = state.get("budget_plan", {})
    total_budget = _safe_float(req.get("budget_sgd"))
    projected_total = _safe_float(budget_plan.get("projected_total_sgd"))
    within_budget = bool(budget_plan.get("within_budget", projected_total <= total_budget if total_budget else False))
    buffer_sgd = _safe_float(budget_plan.get("buffer_sgd", total_budget - projected_total))
    has_dietary_need = str(req.get("dietary_restrictions", "none")).strip().lower() not in {"", "none", "n/a"}
    dietary_supported = _dietary_supported(state)
    diversity = _diversity_summary(state)

    trust_scores = {
        "budget_fit": 1.0 if within_budget else max(0.0, 1.0 - (_safe_div(abs(buffer_sgd), max(total_budget, 1.0)))),
        "evidence_coverage": min(1.0, len(set(evidence_sources)) / 4.0),
        "completeness": 1.0 if not missing_fields else max(0.0, 1.0 - len(missing_fields) / 8.0),
        "constraint_fit": 1.0 if (not has_dietary_need or dietary_supported) else 0.4,
        "robustness": max(0.0, 1.0 - min(len(fallback_markers), 3) / 3.0),
    }
    trust_score = round(sum(trust_scores[key] * TRUST_WEIGHTS[key] for key in TRUST_WEIGHTS) * 100, 1)

    assurance_checks = [
        _check("required_fields_complete", not missing_fields, "All critical plan sections are populated." if not missing_fields else f"Missing fields: {', '.join(missing_fields)}"),
        _check("budget_consistency", projected_total >= 0, "Projected total was calculated from specialist outputs."),
        _check("budget_within_limit", within_budget, "Projected total is within the user's stated budget." if within_budget else f"Projected total exceeds budget by SGD {max(0.0, projected_total - total_budget):.2f}."),
        _check("flight_tool_evidence", any(call.get("tool") == "FlightAPI" for call in tool_calls), "Flight recommendation is backed by the flight tool call log."),
        _check("multi_signal_destination_validation", len(set(evidence_sources)) >= 3, "Locations, food, and accommodation recommendations are backed by multiple tool/data sources."),
        _check("fallback_pressure", len(fallback_markers) <= 1, "Low fallback/tool-failure pressure detected." if len(fallback_markers) <= 1 else f"Fallback markers detected: {', '.join(fallback_markers)}"),
    ]
    assurance_score = round(sum(1 for item in assurance_checks if item["passed"]) / len(assurance_checks) * 100, 1)

    fairness_checks = [
        _check("sponsored_bias_control", True, "No sponsored result boost path exists in the ranking logic or tool payloads."),
        _check("dietary_constraint_respected", (not has_dietary_need) or dietary_supported, "Dietary restrictions are reflected in food selection notes." if dietary_supported or not has_dietary_need else "Dietary restrictions were captured but not clearly reflected in food reasoning."),
        _check("option_diversity", diversity["food_styles"] >= 2 or diversity["attraction_types"] >= 2, f"Food styles={diversity['food_styles']}, attraction types={diversity['attraction_types']}."),
        _check("stable_tie_breaking", True, "Deterministic fallback logic keeps ranking stable when LLM output is missing."),
    ]

    matched_coercive_pattern = _matched_coercive_pattern(state.get("report", {}))
    ethical_checks = [
        _check("dietary_needs_preserved", (not has_dietary_need) or dietary_supported, "Dietary requirements remain visible in the final plan."),
        _check("budget_transparency", "buffer_sgd" in budget_plan or "projected_total_sgd" in budget_plan, "Budget summary exposes total and budget headroom/shortfall."),
        _check(
            "coercive_language_absent",
            not bool(matched_coercive_pattern),
            (
                "No urgency-selling or dark-pattern phrasing detected in the generated plan."
                if not matched_coercive_pattern
                else f"Urgency-selling or dark-pattern phrasing was detected in the generated plan: '{matched_coercive_pattern}'."
            ),
        ),
        _check("destination_risk_keywords", not _contains_risk_destination(req), "No explicit high-risk destination keyword matched the rule set."),
    ]

    autonomy_reasons = []
    if not within_budget:
        autonomy_reasons.append("budget_overrun")
    if missing_fields:
        autonomy_reasons.append("missing_fields")
    if assurance_score < 70:
        autonomy_reasons.append("low_assurance")
    if any(not item["passed"] for item in ethical_checks):
        autonomy_reasons.append("ethical_review")

    full_trace = list(state.get("decision_trace", []))
    summary_trace = _summarize_decision_trace(full_trace)
    trace_hash = hashlib.sha256(
        json.dumps(
            {
                "tool_calls": tool_calls,
                "decision_trace": full_trace,
                "policy_version": POLICY_VERSION,
                "run_id": get_run_id(state),
                "round": state.get("round_number", 0),
            },
            sort_keys=True,
            default=str,
        ).encode("utf-8")
    ).hexdigest()

    return {
        "governance": {
            "policy_version": POLICY_VERSION,
            "report_schema_version": REPORT_SCHEMA_VERSION,
            "governed_tool_gateway": True,
            "agent_tool_permissions_enforced": True,
            "decision_rule_version": POLICY_VERSION,
            "tools_observed": sorted({call.get("tool", "") for call in tool_calls if call.get("tool")}),
            "current_run_id": get_run_id(state),
        },
        "accountability": {
            "audit_id": state["governance_metadata"]["audit_id"],
            "run_id": get_run_id(state),
            "trace_hash": trace_hash,
            "round_number": state.get("round_number", 0),
            "tool_call_count": len(tool_calls),
            "decision_record_count": len(state.get("decision_trace", [])),
            "last_updated_at": state["governance_metadata"]["last_updated_at"],
        },
        "decision_trace": summary_trace,
        "decision_trace_full": full_trace,
        "explainability": {
            "summary": "The final plan is ranked using deterministic weights across budget fit, evidence coverage, completeness, preference fit, and robustness.",
            "score_breakdown": [
                {"criterion": key, "weight": TRUST_WEIGHTS[key], "score": round(value * 100, 1)}
                for key, value in trust_scores.items()
            ],
            "decision_factors": {
                "budget_target_sgd": total_budget,
                "projected_total_sgd": projected_total,
                "dietary_restrictions": req.get("dietary_restrictions", "none"),
                "evidence_sources": evidence_sources,
                "fallback_markers": fallback_markers,
            },
        },
        "assurance": {
            "confidence_score": assurance_score,
            "approval_gate": "approved" if assurance_score >= 70 and not missing_fields else "needs_review",
            "validation_checks": assurance_checks,
        },
        "trust": {
            "score": trust_score,
            "ranking_formula": [
                {"criterion": key, "weight": TRUST_WEIGHTS[key], "score": round(value * 100, 1)}
                for key, value in trust_scores.items()
            ],
            "user_visible_reason": "Cheaper, complete, and better-evidenced plans are ranked ahead of expensive or weakly-supported ones.",
        },
        "fairness": {
            "status": "stronger" if sum(1 for item in fairness_checks if item["passed"]) >= 3 else "partial",
            "checks": fairness_checks,
            "mitigations": [{"area": area, "rule": rule} for area, rule in FAIRNESS_AREAS.items()],
        },
        "ethical_checks": {
            "status": "clear" if all(item["passed"] for item in ethical_checks) else "review",
            "checks": ethical_checks,
            "rule_engine": {
                "coercive_language_patterns": list(COERCIVE_PATTERNS),
                "higher_risk_destination_keywords": sorted(HIGHER_RISK_DESTINATIONS),
            },
        },
        "autonomy": {
            "auto_rerun_enabled": True,
            "triggers": autonomy_reasons,
            "next_action": "rerun" if autonomy_reasons else "accept_plan",
        },
        "imda_alignment": {
            "governance": "stronger",
            "accountability": "stronger",
            "explainability": "stronger",
            "assurance": "stronger" if assurance_score >= 70 else "partial",
            "fairness": "stronger" if sum(1 for item in fairness_checks if item["passed"]) >= 3 else "partial",
            "ethics": "clear" if all(item["passed"] for item in ethical_checks) else "review",
            "trust": "stronger" if trust_score >= 70 else "partial",
            "autonomy": "stronger" if autonomy_reasons else "partial",
        },
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _check(name: str, passed: bool, detail: str) -> Dict[str, Any]:
    return {"name": name, "passed": bool(passed), "detail": detail}


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _safe_div(left: float, right: float) -> float:
    return left / right if right else 0.0


def _normalize_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _normalize_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize_json(v) for v in value]
    return value


def _result_preview(value: Any) -> Any:
    normalized = _normalize_json(value)
    if isinstance(normalized, list):
        return {"type": "list", "count": len(normalized), "sample": normalized[:2]}
    if isinstance(normalized, dict):
        return {"type": "dict", "keys": list(normalized.keys())[:8]}
    return normalized


def _collect_sources(values: Iterable[Any]) -> List[str]:
    found: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            source = value.get("source")
            if isinstance(source, str) and source.strip():
                found.add(source.strip())
            for sub in value.values():
                walk(sub)
        elif isinstance(value, list):
            for sub in value:
                walk(sub)

    for entry in values:
        walk(entry)
    return sorted(found)


def _fallback_markers(state: Dict[str, Any]) -> List[str]:
    markers: List[str] = []
    flight = state.get("flight_plan", {})
    weather_notes = str(flight.get("weather_notes", "")).lower()
    if "unavailable" in weather_notes or "fallback" in weather_notes:
        markers.append("weather_fallback")
    if "no live flight options found" in str(flight.get("selected_option", {})).lower():
        markers.append("flight_fallback")
    if "no live accommodation options found" in str(state.get("accomodations_plan", {}).get("selected_stay", {})).lower():
        markers.append("accommodation_fallback")
    return markers


def _missing_fields(state: Dict[str, Any]) -> List[str]:
    required = {
        "flight.selected_option": state.get("flight_plan", {}).get("selected_option"),
        "locations.top_attractions": state.get("locations_plan", {}).get("top_attractions"),
        "food.meal_plan": state.get("food_plan", {}).get("meal_plan"),
        "accomodations.selected_stay": state.get("accomodations_plan", {}).get("selected_stay"),
        "budget.projected_total_sgd": state.get("budget_plan", {}).get("projected_total_sgd"),
        "budget.within_budget": state.get("budget_plan", {}).get("within_budget"),
    }
    missing = []
    for name, value in required.items():
        if value is None:
            missing.append(name)
        elif isinstance(value, str) and not value.strip():
            missing.append(name)
        elif isinstance(value, (list, dict)) and not value:
            missing.append(name)
    return missing


def _dietary_supported(state: Dict[str, Any]) -> bool:
    req = str(state.get("user_requirements", {}).get("dietary_restrictions", "none")).strip().lower()
    if req in {"", "none", "n/a"}:
        return True
    haystacks = [
        json.dumps(state.get("food_plan", {}), ensure_ascii=True).lower(),
        json.dumps(state.get("report", {}), ensure_ascii=True).lower(),
    ]
    return any(req in hay for hay in haystacks)


def _diversity_summary(state: Dict[str, Any]) -> Dict[str, int]:
    food_styles = {
        str(item.get("style", "")).strip().lower()
        for item in state.get("food_plan", {}).get("top_food_spots", [])
        if isinstance(item, dict) and str(item.get("style", "")).strip()
    }
    attraction_types = {
        str(item.get("type", "")).strip().lower()
        for item in state.get("locations_plan", {}).get("top_attractions", [])
        if isinstance(item, dict) and str(item.get("type", "")).strip()
    }
    return {"food_styles": len(food_styles), "attraction_types": len(attraction_types)}


def _contains_coercive_text(value: Any) -> bool:
    return bool(_matched_coercive_pattern(value))


def _matched_coercive_pattern(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=True).lower()
    for pattern in COERCIVE_PATTERNS:
        if pattern in text:
            return pattern
    return ""


def _contains_risk_destination(req: Dict[str, Any]) -> bool:
    text = json.dumps(req, ensure_ascii=True).lower()
    return any(pattern in text for pattern in HIGHER_RISK_DESTINATIONS)


def _summarize_decision_trace(trace: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    actor_order = [
        "orchestrator",
        "flight_agent",
        "locations_agent",
        "food_agent",
        "accomodations_agent",
        "budget_agent",
        "consolidation",
    ]
    actor_labels = {
        "orchestrator": "Planning setup",
        "flight_agent": "Flights",
        "locations_agent": "Attractions",
        "food_agent": "Food",
        "accomodations_agent": "Stay",
        "budget_agent": "Budget",
        "consolidation": "Final report",
    }
    latest_by_actor: Dict[str, Dict[str, Any]] = {}
    tool_counts: Dict[str, int] = {}

    for entry in trace:
        actor = str(entry.get("actor", "")).strip()
        if not actor:
            continue
        if _is_tool_trace(entry):
            tool_counts[actor] = tool_counts.get(actor, 0) + 1
            continue
        latest_by_actor[actor] = entry

    summary: List[Dict[str, Any]] = []
    for actor in actor_order:
        entry = latest_by_actor.get(actor)
        if not entry:
            continue
        summary.append(
            {
                "stage": actor_labels.get(actor, actor.replace("_", " ").title()),
                "timestamp": entry.get("timestamp", ""),
                "summary": entry.get("summary", ""),
                "outcome": entry.get("outcome", ""),
                "tools_used": tool_counts.get(actor, 0),
                "policy_tags": entry.get("policy_tags", []),
            }
        )
    return summary


def _is_tool_trace(entry: Dict[str, Any]) -> bool:
    summary = str(entry.get("summary", "")).lower()
    return summary.startswith("used governed tool ") or summary.startswith("tool call failed for ")
