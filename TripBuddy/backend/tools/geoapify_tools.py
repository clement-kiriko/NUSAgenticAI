import os
import logging
import math
import time
from typing import Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

logger = logging.getLogger(__name__)

_GEOAPIFY_ROUTING_DISTANCE_LIMIT_M = 10_000_000


def _mask_api_key(url: str) -> str:
    parts = urlsplit(url)
    query = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key == "apiKey" and value:
            value = f"{value[:4]}...{value[-4:]}" if len(value) > 8 else "***"
        query.append((key, value))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _geoapify_get(url: str, params: dict, timeout: int, log_name: str) -> httpx.Response:
    started_at = time.monotonic()
    resp = httpx.get(url, params=params, timeout=timeout)
    elapsed_ms = round((time.monotonic() - started_at) * 1000, 1)
    logger.info(
        "%s completed status=%s elapsed_ms=%s url=%s body=%s",
        log_name,
        resp.status_code,
        elapsed_ms,
        _mask_api_key(str(resp.request.url)),
        resp.text[:500],
    )
    resp.raise_for_status()
    return resp


def _haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    radius_m = 6_371_000
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(radius_m * c)


def _routing_limit_exceeded(exc: httpx.HTTPStatusError) -> bool:
    if exc.response is None or exc.response.status_code != 400:
        return False

    try:
        payload = exc.response.json()
    except ValueError:
        payload = {}

    message = ""
    if isinstance(payload, dict):
        message = str(payload.get("message", ""))
    if not message:
        message = exc.response.text

    lowered = message.lower()
    return "distance should not exceed" in lowered and "estimated distance is" in lowered


def _geoapify_geocode(query: str, key: str) -> Optional[Dict]:
    resp = _geoapify_get(
        "https://api.geoapify.com/v1/geocode/search",
        {"text": query, "limit": 1, "apiKey": key},
        timeout=10,
        log_name=f"Geoapify geocode query={query}",
    )
    features = resp.json().get("features", [])
    if not features:
        return None
    feature = features[0]
    coords = feature.get("geometry", {}).get("coordinates", [])
    if len(coords) != 2:
        return None
    props = feature.get("properties", {})
    return {
        "lon": coords[0],
        "lat": coords[1],
        "country": props.get("country"),
        "city": props.get("city"),
        "formatted": props.get("formatted"),
    }


def _geoapify_places(lon: float, lat: float, categories: str, key: str, limit: int = 6) -> List[Dict]:
    resp = _geoapify_get(
        "https://api.geoapify.com/v2/places",
        {
            "categories": categories,
            "filter": f"circle:{lon},{lat},8000",
            "bias": f"proximity:{lon},{lat}",
            "limit": limit,
            "apiKey": key,
        },
        timeout=15,
        log_name=f"Geoapify places categories={categories}",
    )
    return resp.json().get("features", [])


def _first_category(props: Dict) -> str:
    categories = props.get("categories", [])
    if categories:
        return str(categories[0]).split(".")[-1].replace("_", "-")
    return "general"


def _contains_category(props: Dict, category_fragment: str) -> bool:
    return category_fragment in str(props.get("categories", []))


# def flight_api(origin: str, destination: str, days: int) -> List[Dict]:
#     base = 420 + (days * 18)
#     return [
#         {
#             "airline": "SkyWays",
#             "route": f"{origin} -> {destination}",
#             "price_sgd": base,
#             "stops": 0,
#         },
#         {
#             "airline": "AeroConnect",
#             "route": f"{origin} -> {destination}",
#             "price_sgd": base - 70,
#             "stops": 1,
#         },
#     ]


# def weather_api(destination: str) -> Dict:
#     return {
#         "destination": destination,
#         "forecast": "Warm with occasional showers",
#         "temperature_c": "24-31",
#     }


def tourist_attraction_api(destination: str) -> List[Dict]:
    key = os.getenv("GEOAPIFY_API_KEY", "").strip()
    if key:
        try:
            geo = _geoapify_geocode(destination, key)
            if geo:
                features = _geoapify_places(
                    geo["lon"],
                    geo["lat"],
                    "tourism.attraction,tourism.sights,entertainment.museum",
                    key,
                    limit=6,
                )
                rows = []
                for item in features:
                    props = item.get("properties", {})
                    ticket = 15
                    if _contains_category(props, "museum"):
                        ticket = 25
                    rows.append(
                        {
                            "name": props.get("name", props.get("formatted", "Unknown attraction")),
                            "type": _first_category(props),
                            "ticket_sgd": ticket,
                            "destination": destination,
                            "source": "geoapify",
                        }
                    )
                if rows:
                    return rows
        except Exception:
            logger.exception("Tourist attraction lookup failed destination=%s", destination)

    defaults = [
        {"name": "Central Heritage District", "type": "culture", "ticket_sgd": 25, "source": "mock"},
        {"name": "City Observation Deck", "type": "scenic", "ticket_sgd": 40, "source": "mock"},
        {"name": "Night Market Street", "type": "food-shopping", "ticket_sgd": 0, "source": "mock"},
    ]
    return [{**item, "destination": destination} for item in defaults]


def food_api(destination: str) -> List[Dict]:
    key = os.getenv("GEOAPIFY_API_KEY", "").strip()
    if key:
        try:
            geo = _geoapify_geocode(destination, key)
            if geo:
                features = _geoapify_places(
                    geo["lon"],
                    geo["lat"],
                    "catering.restaurant,catering.fast_food,catering.cafe",
                    key,
                    limit=6,
                )
                rows = []
                for item in features:
                    props = item.get("properties", {})
                    est_cost = 28
                    if _contains_category(props, "fast_food"):
                        est_cost = 12
                    elif _contains_category(props, "cafe"):
                        est_cost = 18
                    rows.append(
                        {
                            "name": props.get("name", props.get("formatted", "Unknown food spot")),
                            "style": _first_category(props),
                            "cost_per_meal_sgd": est_cost,
                            "destination": destination,
                            "source": "geoapify",
                        }
                    )
                if rows:
                    return rows
        except Exception:
            logger.exception("Food catalog lookup failed destination=%s", destination)

    return [
        {
            "name": "Local Hawker Classics",
            "style": "local",
            "cost_per_meal_sgd": 12,
            "destination": destination,
            "source": "mock",
        },
        {
            "name": "Mid-range Bistro",
            "style": "international",
            "cost_per_meal_sgd": 28,
            "destination": destination,
            "source": "mock",
        },
        {
            "name": "Diet-friendly Cafe",
            "style": "healthy",
            "cost_per_meal_sgd": 22,
            "destination": destination,
            "source": "mock",
        },
    ]


def accomodation_api(destination: str) -> List[Dict]:
    key = os.getenv("GEOAPIFY_API_KEY", "").strip()
    if key:
        try:
            geo = _geoapify_geocode(destination, key)
            if geo:
                features = _geoapify_places(
                    geo["lon"],
                    geo["lat"],
                    "accommodation.hotel,accommodation.hostel,accommodation.guest_house",
                    key,
                    limit=6,
                )
                rows = []
                for item in features:
                    props = item.get("properties", {})
                    nightly = 145
                    if _contains_category(props, "hostel"):
                        nightly = 60
                    elif _contains_category(props, "guest_house"):
                        nightly = 110
                    rows.append(
                        {
                            "name": props.get("name", props.get("formatted", "Unknown stay")),
                            "type": _first_category(props),
                            "nightly_rate_sgd": nightly,
                            "destination": destination,
                            "source": "geoapify",
                        }
                    )
                if rows:
                    return rows
        except Exception:
            logger.exception("Accommodation lookup failed destination=%s", destination)

    return [
        {
            "name": "City Capsule Inn",
            "type": "budget",
            "nightly_rate_sgd": 60,
            "destination": destination,
            "source": "mock",
        },
        {
            "name": "Riverside Hotel",
            "type": "mid-range",
            "nightly_rate_sgd": 145,
            "destination": destination,
            "source": "mock",
        },
        {
            "name": "Skyline Suites",
            "type": "premium",
            "nightly_rate_sgd": 260,
            "destination": destination,
            "source": "mock",
        },
    ]


def web_search_api(query: str, limit: int = 5) -> List[Dict]:
    """
    Retrieval tool: uses Geoapify place search when GEOAPIFY_API_KEY is present.
    Falls back to local mock search snippets when key is missing/unavailable.
    """
    key = os.getenv("GEOAPIFY_API_KEY", "").strip()
    if key:
        url = "https://api.geoapify.com/v1/geocode/search"
        params = {"text": query, "limit": limit, "apiKey": key}
        try:
            response = _geoapify_get(url, params, timeout=10, log_name=f"Geoapify web search query={query}")
            data = response.json()
            rows = []
            for feature in data.get("features", []):
                props = feature.get("properties", {})
                rows.append(
                    {
                        "name": props.get("formatted", "Unknown"),
                        "country": props.get("country"),
                        "city": props.get("city"),
                        "source": "geoapify",
                    }
                )
            if rows:
                return rows
        except Exception:
            logger.exception("Web search lookup failed query=%s", query)

    return [
        {"name": f"{query} - Top Pick 1", "snippet": "Highly rated by travelers", "source": "mock"},
        {"name": f"{query} - Top Pick 2", "snippet": "Popular and centrally located", "source": "mock"},
        {"name": f"{query} - Top Pick 3", "snippet": "Good value for budget travelers", "source": "mock"},
    ][:limit]


def maps_api(origin: str, destination: str) -> Dict:
    """
    Retrieval tool: stub for transit/geospatial reasoning.
    Replace with a paid maps routing API for production.
    """
    key = os.getenv("GEOAPIFY_API_KEY", "").strip()
    if key:
        try:
            geo_url = "https://api.geoapify.com/v1/geocode/search"
            origin_resp = _geoapify_get(
                geo_url,
                {"text": origin, "limit": 1, "apiKey": key},
                timeout=10,
                log_name=f"Geoapify route geocode origin={origin}",
            )
            dest_resp = _geoapify_get(
                geo_url,
                {"text": destination, "limit": 1, "apiKey": key},
                timeout=10,
                log_name=f"Geoapify route geocode destination={destination}",
            )
            o = origin_resp.json().get("features", [{}])[0].get("geometry", {}).get("coordinates", [])
            d = dest_resp.json().get("features", [{}])[0].get("geometry", {}).get("coordinates", [])
            if len(o) == 2 and len(d) == 2:
                distance_m = _haversine_distance_m(o[1], o[0], d[1], d[0])
                if distance_m > _GEOAPIFY_ROUTING_DISTANCE_LIMIT_M:
                    return {
                        "origin": origin,
                        "destination": destination,
                        "typical_taxi_minutes": None,
                        "distance_km": round(distance_m / 1000, 1),
                        "source": "geoapify_distance_fallback",
                        "note": "Straight-line estimate used because route exceeds Geoapify distance limit.",
                    }

                try:
                    route_resp = _geoapify_get(
                        "https://api.geoapify.com/v1/routing",
                        {
                            "waypoints": f"{o[1]},{o[0]}|{d[1]},{d[0]}",
                            "mode": "drive",
                            "apiKey": key,
                        },
                        timeout=15,
                        log_name=f"Geoapify routing origin={origin} destination={destination}",
                    )
                except httpx.HTTPStatusError as exc:
                    if _routing_limit_exceeded(exc):
                        logger.warning(
                            "Geoapify routing limit exceeded origin=%s destination=%s distance_m=%s",
                            origin,
                            destination,
                            distance_m,
                        )
                        return {
                            "origin": origin,
                            "destination": destination,
                            "typical_taxi_minutes": None,
                            "distance_km": round(distance_m / 1000, 1),
                            "source": "geoapify_distance_fallback",
                            "note": "Straight-line estimate used because route exceeds Geoapify distance limit.",
                        }
                    raise

                features = route_resp.json().get("features", [])
                if features:
                    props = features[0].get("properties", {})
                    duration_sec = props.get("time", 0)
                    route_distance_m = props.get("distance", 0)
                    return {
                        "origin": origin,
                        "destination": destination,
                        "typical_taxi_minutes": round(duration_sec / 60) if duration_sec else None,
                        "distance_km": round(route_distance_m / 1000, 1) if route_distance_m else round(distance_m / 1000, 1),
                        "source": "geoapify",
                    }
        except Exception:
            logger.exception("Maps lookup failed origin=%s destination=%s", origin, destination)

    return {
        "origin": origin,
        "destination": destination,
        "typical_transit_minutes": 35,
        "typical_taxi_minutes": 20,
        "source": "mock_maps",
    }


def reviews_api(query: str, limit: int = 5) -> List[Dict]:
    """
    Retrieval tool: place signals from Geoapify Places API.
    Geoapify does not provide Yelp-style review text; this returns popularity proxies.
    """
    key = os.getenv("GEOAPIFY_API_KEY", "").strip()
    if key:
        try:
            geo_resp = _geoapify_get(
                "https://api.geoapify.com/v1/geocode/search",
                {"text": query, "limit": 1, "apiKey": key},
                timeout=10,
                log_name=f"Geoapify reviews geocode query={query}",
            )
            features = geo_resp.json().get("features", [])
            if features:
                coords = features[0].get("geometry", {}).get("coordinates", [])
                if len(coords) == 2:
                    lon, lat = coords
                    places_resp = _geoapify_get(
                        "https://api.geoapify.com/v2/places",
                        {
                            "categories": "accommodation.hotel,catering.restaurant,tourism.attraction",
                            "filter": f"circle:{lon},{lat},4000",
                            "bias": f"proximity:{lon},{lat}",
                            "limit": limit,
                            "apiKey": key,
                        },
                        timeout=15,
                        log_name=f"Geoapify reviews places query={query}",
                    )
                    rows = []
                    for item in places_resp.json().get("features", []):
                        props = item.get("properties", {})
                        rows.append(
                            {
                                "place": props.get("name", props.get("formatted", "Unknown")),
                                "category": props.get("categories", [])[:2],
                                "address": props.get("formatted"),
                                "source": "geoapify",
                            }
                        )
                    if rows:
                        return rows
        except Exception:
            logger.exception("Reviews lookup failed query=%s", query)

    return [
        {"place": f"{query} Spot A", "category": ["fallback"], "source": "mock_reviews"},
        {"place": f"{query} Spot B", "category": ["fallback"], "source": "mock_reviews"},
        {"place": f"{query} Spot C", "category": ["fallback"], "source": "mock_reviews"},
    ][:limit]
