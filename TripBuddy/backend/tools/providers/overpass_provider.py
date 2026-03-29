import logging
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "DiningSearchAgent/1.0 (00clement.tay@gmail.com)"}

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]


def _mask_query_value(url: str, field: str) -> str:
    parts = urlsplit(url)
    query = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key == field and value:
            value = f"{value[:4]}...{value[-4:]}" if len(value) > 8 else "***"
        query.append((key, value))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def nominatim_geocode(location: str, timeout: int = 10) -> dict | None:
    started_at = time.monotonic()
    resp = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": location, "format": "json", "limit": 1},
        headers=HEADERS,
        timeout=timeout,
    )
    elapsed_ms = round((time.monotonic() - started_at) * 1000, 1)
    logger.info(
        "Nominatim geocode completed query=%s status=%s elapsed_ms=%s url=%s body=%s",
        location,
        resp.status_code,
        elapsed_ms,
        _mask_query_value(resp.request.url, "q"),
        resp.text[:500],
    )
    data = resp.json()
    if not data:
        logger.warning("Nominatim geocode returned no results query=%s", location)
        return None
    return {"lat": data[0]["lat"], "lon": data[0]["lon"]}


def overpass_dining(lat: str, lon: str, radius_m: int, limit: int, timeout: int = 30) -> list[dict]:
    query = f"""
[out:json][timeout:25];
(
  node["amenity"="restaurant"](around:{radius_m},{lat},{lon});
  node["amenity"="cafe"](around:{radius_m},{lat},{lon});
  node["amenity"="fast_food"](around:{radius_m},{lat},{lon});
);
out body {limit * 2};
"""
    elements: list[dict] = []
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            logger.info("Overpass request started endpoint=%s radius_m=%s limit=%s", endpoint, radius_m, limit)
            started_at = time.monotonic()
            resp = requests.post(endpoint, data={"data": query}, timeout=timeout)
            elapsed_ms = round((time.monotonic() - started_at) * 1000, 1)
            if resp.status_code == 200 and resp.text.strip():
                elements = resp.json().get("elements", [])
                logger.info(
                    "Overpass request completed endpoint=%s status=%s elapsed_ms=%s elements=%s",
                    endpoint,
                    resp.status_code,
                    elapsed_ms,
                    len(elements),
                )
                break
            logger.warning(
                "Overpass request returned unusable response endpoint=%s status=%s elapsed_ms=%s body=%s",
                endpoint,
                resp.status_code,
                elapsed_ms,
                resp.text[:500],
            )
            time.sleep(2)
        except Exception as exc:
            logger.warning("Overpass request failed endpoint=%s error=%s", endpoint, exc)
            time.sleep(2)
    return elements
