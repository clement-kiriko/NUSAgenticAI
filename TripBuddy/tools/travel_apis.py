import os
from typing import Dict, List

import httpx


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
    defaults = [
        {"name": "Central Heritage District", "type": "culture", "ticket_sgd": 25},
        {"name": "City Observation Deck", "type": "scenic", "ticket_sgd": 40},
        {"name": "Night Market Street", "type": "food-shopping", "ticket_sgd": 0},
    ]
    return [{**item, "destination": destination} for item in defaults]


def food_api(destination: str) -> List[Dict]:
    return [
        {"name": "Local Hawker Classics", "style": "local", "cost_per_meal_sgd": 12, "destination": destination},
        {"name": "Mid-range Bistro", "style": "international", "cost_per_meal_sgd": 28, "destination": destination},
        {"name": "Diet-friendly Cafe", "style": "healthy", "cost_per_meal_sgd": 22, "destination": destination},
    ]


def accomodation_api(destination: str) -> List[Dict]:
    return [
        {"name": "City Capsule Inn", "type": "budget", "nightly_rate_sgd": 60, "destination": destination},
        {"name": "Riverside Hotel", "type": "mid-range", "nightly_rate_sgd": 145, "destination": destination},
        {"name": "Skyline Suites", "type": "premium", "nightly_rate_sgd": 260, "destination": destination},
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
            response = httpx.get(url, params=params, timeout=10)
            response.raise_for_status()
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
            pass

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
            origin_resp = httpx.get(
                geo_url, params={"text": origin, "limit": 1, "apiKey": key}, timeout=10
            )
            dest_resp = httpx.get(
                geo_url, params={"text": destination, "limit": 1, "apiKey": key}, timeout=10
            )
            origin_resp.raise_for_status()
            dest_resp.raise_for_status()
            o = origin_resp.json().get("features", [{}])[0].get("geometry", {}).get("coordinates", [])
            d = dest_resp.json().get("features", [{}])[0].get("geometry", {}).get("coordinates", [])
            if len(o) == 2 and len(d) == 2:
                route_resp = httpx.get(
                    "https://api.geoapify.com/v1/routing",
                    params={
                        "waypoints": f"{o[1]},{o[0]}|{d[1]},{d[0]}",
                        "mode": "drive",
                        "apiKey": key,
                    },
                    timeout=15,
                )
                route_resp.raise_for_status()
                features = route_resp.json().get("features", [])
                if features:
                    props = features[0].get("properties", {})
                    duration_sec = props.get("time", 0)
                    distance_m = props.get("distance", 0)
                    return {
                        "origin": origin,
                        "destination": destination,
                        "typical_taxi_minutes": round(duration_sec / 60) if duration_sec else None,
                        "distance_km": round(distance_m / 1000, 1) if distance_m else None,
                        "source": "geoapify",
                    }
        except Exception:
            pass

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
            geo_resp = httpx.get(
                "https://api.geoapify.com/v1/geocode/search",
                params={"text": query, "limit": 1, "apiKey": key},
                timeout=10,
            )
            geo_resp.raise_for_status()
            features = geo_resp.json().get("features", [])
            if features:
                coords = features[0].get("geometry", {}).get("coordinates", [])
                if len(coords) == 2:
                    lon, lat = coords
                    places_resp = httpx.get(
                        "https://api.geoapify.com/v2/places",
                        params={
                            "categories": "accommodation.hotel,catering.restaurant,tourism.attraction",
                            "filter": f"circle:{lon},{lat},4000",
                            "bias": f"proximity:{lon},{lat}",
                            "limit": limit,
                            "apiKey": key,
                        },
                        timeout=15,
                    )
                    places_resp.raise_for_status()
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
            pass

    return [
        {"place": f"{query} Spot A", "category": ["fallback"], "source": "mock_reviews"},
        {"place": f"{query} Spot B", "category": ["fallback"], "source": "mock_reviews"},
        {"place": f"{query} Spot C", "category": ["fallback"], "source": "mock_reviews"},
    ][:limit]
