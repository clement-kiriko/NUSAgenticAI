import datetime
import logging
import os
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests

logger = logging.getLogger(__name__)


def _mask_api_key(url: str) -> str:
    parts = urlsplit(url)
    query = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key == "access_key" and value:
            value = f"{value[:4]}...{value[-4:]}" if len(value) > 8 else "***"
        query.append((key, value))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _fallback_flights(origin: str, destination: str, reason: str) -> list[dict]:
    logger.warning(
        "Aviationstack fallback used origin=%s destination=%s reason=%s",
        origin,
        destination,
        reason,
    )
    return []


def flight_api(origin: str, destination: str, days: int):
    api_key = (os.getenv("AVIATIONSTACK_API_KEY") or "").strip()
    if not api_key:
        return _fallback_flights(origin, destination, "missing AVIATIONSTACK_API_KEY")

    departure_date = (datetime.date.today() + datetime.timedelta(days=days)).isoformat()
    url = "http://api.aviationstack.com/v1/flights"
    params = {
        "access_key": api_key,
        "dep_iata": origin,
        "arr_iata": destination,
        "flight_date": departure_date,
    }

    started_at = time.monotonic()
    try:
        response = requests.get(url, params=params, timeout=20)
    except requests.RequestException as exc:
        return _fallback_flights(origin, destination, f"request failed: {exc}")
    elapsed_ms = round((time.monotonic() - started_at) * 1000, 1)
    logger.info(
        "Aviationstack request completed origin=%s destination=%s status=%s elapsed_ms=%s url=%s body=%s",
        origin,
        destination,
        response.status_code,
        elapsed_ms,
        _mask_api_key(response.request.url),
        response.text[:500],
    )

    try:
        data = response.json()
    except ValueError:
        return _fallback_flights(origin, destination, f"non-JSON response status={response.status_code}")

    if isinstance(data, dict) and data.get("error"):
        error_info = data.get("error", {}).get("message") or data.get("error", {}).get("info") or "api error"
        return _fallback_flights(origin, destination, f"api error status={response.status_code}: {error_info}")

    return [
        {
            "airline": flight["airline"]["name"],
            "flight_number": flight["flight"]["iata"],
            "departure_time": flight["departure"]["scheduled"],
            "arrival_time": flight["arrival"]["scheduled"],
        }
        for flight in data.get("data", [])
        if flight.get("airline")
    ]
