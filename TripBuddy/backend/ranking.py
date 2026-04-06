from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime
from typing import Any, Dict, Iterable, List, Tuple


SOURCE_PRIORITY = {
    "geoapify": 0,
    "geoapify_distance_fallback": 1,
    "mock": 2,
    "mock_reviews": 3,
    "mock_maps": 4,
    "aviationstack": 0,
}


def normalize_candidate(
    item: Dict[str, Any],
    *,
    kind: str,
    index: int,
    provider: str | None = None,
) -> Dict[str, Any]:
    source = str(item.get("source") or provider or "unknown").strip().lower()
    provider_name = str(item.get("provider") or provider or source or "unknown").strip().lower()
    name = str(
        item.get("name")
        or item.get("flight_number")
        or item.get("route")
        or item.get("place")
        or f"{kind}-{index}"
    ).strip()
    candidate_id = str(item.get("id") or f"{kind}:{provider_name}:{name}:{index}")
    category = _candidate_category(item, kind)
    dietary_tags = _listify(item.get("dietary_tags"))
    accessibility_tags = _listify(item.get("accessibility_tags"))
    estimated_price = _candidate_price(item, kind)
    travel_time_min = _candidate_travel_time(item)
    rating = _safe_float_or_none(item.get("rating"))
    review_count = _safe_int_or_none(item.get("review_count"))
    evidence_count = _safe_int_or_none(item.get("evidence_count")) or 1
    location_area = str(item.get("location_area") or item.get("destination") or "").strip()

    normalized = {
        "id": candidate_id,
        "source": source,
        "provider": provider_name,
        "is_sponsored": _normalize_sponsorship(item.get("is_sponsored")),
        "estimated_price_sgd": estimated_price,
        "travel_time_min": travel_time_min,
        "rating": rating,
        "review_count": review_count,
        "category": category,
        "dietary_tags": dietary_tags,
        "accessibility_tags": accessibility_tags,
        "location_area": location_area,
        "evidence_count": evidence_count,
        "raw": dict(item),
    }
    return normalized


def rank_candidates(
    candidates: Iterable[Dict[str, Any]],
    *,
    kind: str,
    user_requirements: Dict[str, Any] | None = None,
    top_k: int | None = None,
    diversity_key: str | None = None,
    seed_hint: str = "",
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    req = user_requirements or {}
    normalized = [normalize_candidate(item, kind=kind, index=index) for index, item in enumerate(candidates)]
    filtered = [item for item in normalized if _passes_hard_constraints(item, kind=kind, user_requirements=req)]

    if not filtered:
        filtered = normalized

    scored: List[Dict[str, Any]] = []
    seed = _stable_seed(kind=kind, user_requirements=req, seed_hint=seed_hint, candidates=filtered)
    for item in filtered:
        score, contributions = _score_candidate(item, kind=kind, user_requirements=req)
        scored.append(
            {
                **item,
                "ranking_score": round(score, 4),
                "score_breakdown": contributions,
                "source_priority": SOURCE_PRIORITY.get(item["source"], 99),
                "seed": seed,
            }
        )

    scored.sort(
        key=lambda item: (
            -item["ranking_score"],
            _null_last_number(item["estimated_price_sgd"]),
            _null_last_number(item["travel_time_min"]),
            item["source_priority"],
            item["id"],
        )
    )

    if diversity_key and top_k and len(scored) > 1:
        selected = select_diverse_top_k(scored, top_k=top_k, diversity_key=diversity_key)
    else:
        selected = scored[:top_k] if top_k else scored

    metadata = {
        "kind": kind,
        "seed": seed,
        "candidate_count": len(normalized),
        "eligible_count": len(filtered),
        "selected_count": len(selected),
        "diversity_key": diversity_key or "",
        "selected_ids": [item["id"] for item in selected],
        "selected_categories": [str(item.get(diversity_key, "")) for item in selected] if diversity_key else [],
        "has_unknown_sponsorship": any(item["is_sponsored"] is None for item in normalized),
        "sponsored_candidates_present": any(item["is_sponsored"] is True for item in normalized),
        "selection_mode": "deterministic_seeded_rotation" if diversity_key else "deterministic_stable_sort",
    }
    return selected, metadata


def select_diverse_top_k(candidates: List[Dict[str, Any]], *, top_k: int, diversity_key: str) -> List[Dict[str, Any]]:
    if top_k <= 0:
        return []

    selected: List[Dict[str, Any]] = []
    seen_values: set[str] = set()

    for item in candidates:
        value = str(item.get(diversity_key, "")).strip().lower()
        if value and value not in seen_values:
            selected.append(item)
            seen_values.add(value)
        if len(selected) >= top_k:
            return selected

    for item in candidates:
        if item in selected:
            continue
        selected.append(item)
        if len(selected) >= top_k:
            break
    return selected


def stable_seeded_order(values: Iterable[Dict[str, Any]], *, seed: str) -> List[Dict[str, Any]]:
    rows = list(values)
    rng = random.Random(seed)
    keyed = []
    for item in rows:
        keyed.append((rng.random(), item))
    keyed.sort(key=lambda pair: (pair[0], str(pair[1].get("id", ""))))
    return [item for _, item in keyed]


def _passes_hard_constraints(item: Dict[str, Any], *, kind: str, user_requirements: Dict[str, Any]) -> bool:
    dietary = user_requirements.get("dietary_restrictions", "none")
    if kind != "food":
        return True

    normalized_req = _normalize_dietary_requirement(dietary)
    if normalized_req in {"", "none", "n/a"}:
        return True

    if normalized_req in json.dumps(item["raw"], ensure_ascii=True).lower():
        return True

    dietary_tags = {tag.lower() for tag in item.get("dietary_tags", [])}
    # Preserve prior behavior when metadata is sparse by allowing unknowns through.
    return not dietary_tags or normalized_req in dietary_tags


def _score_candidate(item: Dict[str, Any], *, kind: str, user_requirements: Dict[str, Any]) -> Tuple[float, List[Dict[str, Any]]]:
    contributions: List[Dict[str, Any]] = []
    score = 0.0

    price_weight = 0.45 if kind in {"food", "location", "accommodation", "flight"} else 0.35
    time_weight = 0.2 if kind in {"flight", "accommodation"} else 0.05
    evidence_weight = 0.1
    rating_weight = 0.15
    source_weight = 0.1

    price_component = _inverse_price_score(item.get("estimated_price_sgd"))
    score += price_component * price_weight
    contributions.append({"criterion": "price", "value": round(price_component * price_weight, 4)})

    time_component = _inverse_time_score(item.get("travel_time_min"))
    score += time_component * time_weight
    contributions.append({"criterion": "travel_time", "value": round(time_component * time_weight, 4)})

    rating_component = _rating_score(item.get("rating"), item.get("review_count"))
    score += rating_component * rating_weight
    contributions.append({"criterion": "rating", "value": round(rating_component * rating_weight, 4)})

    source_component = _source_score(item.get("source", ""))
    score += source_component * source_weight
    contributions.append({"criterion": "source", "value": round(source_component * source_weight, 4)})

    evidence_component = min(float(item.get("evidence_count") or 1), 3.0) / 3.0
    score += evidence_component * evidence_weight
    contributions.append({"criterion": "evidence", "value": round(evidence_component * evidence_weight, 4)})

    if item.get("is_sponsored") is True:
        score -= 0.4
        contributions.append({"criterion": "sponsorship_penalty", "value": -0.4})

    dietary = _normalize_dietary_requirement(user_requirements.get("dietary_restrictions", "none"))
    if kind == "food" and dietary not in {"", "none", "n/a"}:
        dietary_tags = {tag.lower() for tag in item.get("dietary_tags", [])}
        if dietary in dietary_tags:
            score += 0.15
            contributions.append({"criterion": "dietary_match", "value": 0.15})

    return score, contributions


def _candidate_category(item: Dict[str, Any], kind: str) -> str:
    if kind == "food":
        return str(item.get("style") or item.get("category") or "general").strip().lower()
    if kind == "location":
        return str(item.get("type") or item.get("category") or "general").strip().lower()
    if kind == "accommodation":
        return str(item.get("type") or item.get("category") or "general").strip().lower()
    return str(item.get("category") or "general").strip().lower()


def _candidate_price(item: Dict[str, Any], kind: str) -> float | None:
    keys = {
        "food": ("estimated_price_sgd", "cost_per_meal_sgd", "price_sgd"),
        "location": ("estimated_price_sgd", "ticket_sgd", "price_sgd"),
        "accommodation": ("estimated_price_sgd", "nightly_rate_sgd", "price_sgd"),
        "flight": ("estimated_price_sgd", "price_sgd"),
    }.get(kind, ("estimated_price_sgd", "price_sgd"))
    for key in keys:
        value = _safe_float_or_none(item.get(key))
        if value is not None:
            return value
    return None


def _candidate_travel_time(item: Dict[str, Any]) -> int | None:
    for key in ("travel_time_min", "typical_taxi_minutes", "duration_min"):
        value = _safe_int_or_none(item.get(key))
        if value is not None:
            return value

    departure = item.get("departure_time")
    arrival = item.get("arrival_time")
    if departure and arrival:
        try:
            dep = datetime.fromisoformat(str(departure).replace("Z", "+00:00"))
            arr = datetime.fromisoformat(str(arrival).replace("Z", "+00:00"))
            minutes = round((arr - dep).total_seconds() / 60)
            return max(minutes, 0)
        except ValueError:
            return None
    return None


def _normalize_sponsorship(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "yes", "promoted", "sponsored", "ad"}:
        return True
    if text in {"false", "no", "organic", "not_sponsored"}:
        return False
    return None


def _normalize_dietary_requirement(value: Any) -> str:
    if isinstance(value, list):
        text = " ".join(str(item) for item in value)
    else:
        text = str(value or "")
    return text.strip().lower()


def _listify(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _safe_float_or_none(value: Any) -> float | None:
    try:
        if value in {"", None}:
            return None
        return float(value)
    except Exception:
        return None


def _safe_int_or_none(value: Any) -> int | None:
    try:
        if value in {"", None}:
            return None
        return int(float(value))
    except Exception:
        return None


def _inverse_price_score(value: float | None) -> float:
    if value is None:
        return 0.5
    return 1.0 / (1.0 + max(value, 0.0) / 100.0)


def _inverse_time_score(value: int | None) -> float:
    if value is None:
        return 0.5
    return 1.0 / (1.0 + max(value, 0) / 120.0)


def _rating_score(rating: float | None, review_count: int | None) -> float:
    if rating is None:
        return 0.5
    capped_reviews = min(max(review_count or 0, 0), 500)
    confidence = capped_reviews / 500.0
    return min(max(rating / 5.0, 0.0), 1.0) * (0.7 + 0.3 * confidence)


def _source_score(source: str) -> float:
    priority = SOURCE_PRIORITY.get(str(source).strip().lower(), 99)
    if priority >= 99:
        return 0.4
    return max(0.2, 1.0 - (priority * 0.15))


def _null_last_number(value: float | int | None) -> float:
    if value is None:
        return float("inf")
    return float(value)


def _stable_seed(
    *,
    kind: str,
    user_requirements: Dict[str, Any],
    seed_hint: str,
    candidates: Iterable[Dict[str, Any]],
) -> str:
    payload = {
        "kind": kind,
        "destination": user_requirements.get("location_preference", ""),
        "days": user_requirements.get("days", 0),
        "seed_hint": seed_hint,
        "candidates": [str(item.get("id", "")) for item in candidates],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:12]
