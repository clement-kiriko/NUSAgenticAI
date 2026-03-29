import logging
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests

logger = logging.getLogger(__name__)


def _mask_api_key(url: str) -> str:
    parts = urlsplit(url)
    query = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key == "apiKey" and value:
            value = f"{value[:4]}...{value[-4:]}" if len(value) > 8 else "***"
        query.append((key, value))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def geoapify_geocode(location: str, api_key: str, timeout: int = 10) -> dict | None:
    started_at = time.monotonic()
    resp = requests.get(
        "https://api.geoapify.com/v1/geocode/search",
        params={"text": location, "limit": 1, "apiKey": api_key},
        timeout=timeout,
    )
    elapsed_ms = round((time.monotonic() - started_at) * 1000, 1)
    logger.info(
        "Geoapify geocode completed query=%s status=%s elapsed_ms=%s url=%s body=%s",
        location,
        resp.status_code,
        elapsed_ms,
        _mask_api_key(resp.request.url),
        resp.text[:500],
    )
    resp.raise_for_status()
    features = resp.json().get("features", [])
    if not features:
        return None

    coords = features[0].get("geometry", {}).get("coordinates", [])
    if len(coords) != 2:
        return None
    lon, lat = coords
    return {"lon": lon, "lat": lat}


def geoapify_places(
    lon: float,
    lat: float,
    categories: str,
    api_key: str,
    limit: int = 10,
    radius_m: int = 5000,
    timeout: int = 15,
) -> list[dict]:
    started_at = time.monotonic()
    resp = requests.get(
        "https://api.geoapify.com/v2/places",
        params={
            "categories": categories,
            "filter": f"circle:{lon},{lat},{radius_m}",
            "bias": f"proximity:{lon},{lat}",
            "limit": limit,
            "apiKey": api_key,
        },
        timeout=timeout,
    )
    elapsed_ms = round((time.monotonic() - started_at) * 1000, 1)
    logger.info(
        "Geoapify places completed categories=%s status=%s elapsed_ms=%s url=%s body=%s",
        categories,
        resp.status_code,
        elapsed_ms,
        _mask_api_key(resp.request.url),
        resp.text[:500],
    )
    resp.raise_for_status()
    return resp.json().get("features", [])
