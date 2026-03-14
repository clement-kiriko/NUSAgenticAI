import time

import requests

HEADERS = {"User-Agent": "DiningSearchAgent/1.0 (00clement.tay@gmail.com)"}

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]


def nominatim_geocode(location: str, timeout: int = 10) -> dict | None:
    resp = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": location, "format": "json", "limit": 1},
        headers=HEADERS,
        timeout=timeout,
    )
    data = resp.json()
    if not data:
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
            print(f"Trying {endpoint}...")
            resp = requests.post(endpoint, data={"data": query}, timeout=timeout)
            if resp.status_code == 200 and resp.text.strip():
                elements = resp.json().get("elements", [])
                print(f"Got {len(elements)} raw elements.")
                break
            print(f"Bad response ({resp.status_code}), trying next endpoint...")
            time.sleep(2)
        except Exception as exc:
            print(f"Error with {endpoint}: {exc}, trying next...")
            time.sleep(2)
    return elements
