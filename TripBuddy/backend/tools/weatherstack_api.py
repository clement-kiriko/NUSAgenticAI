import logging
import os
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests


logger = logging.getLogger(__name__)


def _fallback_weather(city: str, reason: str) -> dict:
    cleaned_city = (city or "").strip() or "the destination"
    logger.warning("Weatherstack fallback used city=%s reason=%s", cleaned_city, reason)
    return {
        "forecast": f"Weather data unavailable for {cleaned_city}; using fallback conditions.",
        "temperature": "N/A",
        "source": "fallback",
        "error": reason,
    }


def _mask_access_key(url: str) -> str:
    parts = urlsplit(url)
    query = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key == "access_key" and value:
            value = f"{value[:4]}...{value[-4:]}" if len(value) > 8 else "***"
        query.append((key, value))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def weather_api(city: str):
    api_key = (os.getenv("WEATHERSTACK_API_KEY") or "").strip()
    if not api_key:
        return _fallback_weather(city, "missing WEATHERSTACK_API_KEY")

    url = "http://api.weatherstack.com/current"
    params = {
        "access_key": api_key,
        "query": (city or "").strip(),
        "units": "m",
    }

    started_at = time.monotonic()
    try:
        response = requests.get(url, params=params, timeout=20)
    except requests.RequestException as exc:
        return _fallback_weather(city, f"request failed: {exc}")

    elapsed_ms = round((time.monotonic() - started_at) * 1000, 1)
    request_url = getattr(getattr(response, "request", None), "url", url)
    masked_url = _mask_access_key(request_url)

    logger.info(
        "Weatherstack request completed city=%s status=%s elapsed_ms=%s url=%s headers=%s proxies=%s body=%s",
        city,
        response.status_code,
        elapsed_ms,
        masked_url,
        dict(getattr(getattr(response, "request", None), "headers", {}) or {}),
        requests.utils.get_environ_proxies(url),
        response.text[:500],
    )

    try:
        data = response.json()
    except ValueError:
        return _fallback_weather(city, f"non-JSON response status={response.status_code}")

    if "current" not in data:
        error_info = data.get("error", {}).get("info") if isinstance(data, dict) else None
        reason = f"api error status={response.status_code}"
        if error_info:
            reason = f"{reason}: {error_info}"
        return _fallback_weather(city, reason)

    return {
        "forecast": data["current"]["weather_descriptions"][0],
        "temperature": f"{data['current']['temperature']} C",
        "source": "weatherstack",
    }
