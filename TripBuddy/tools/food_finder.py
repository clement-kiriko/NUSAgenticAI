
import requests
import time
import argparse

HEADERS = {"User-Agent": "DiningSearchAgent/1.0 (00clement.tay@gmail.com)"}

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]


def search_dining(location: str, radius_m: int = 500, limit: int = 5) -> list[dict]:
    # Step 1: Geocode location to lat/lon
    geo = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": location, "format": "json", "limit": 1},
        headers=HEADERS,
        timeout=10
    ).json()

    if not geo:
        raise ValueError(f"Could not find location: {location}")

    lat, lon = geo[0]["lat"], geo[0]["lon"]
    print(f"Geocoded '{location}' -> lat={lat}, lon={lon}")

    # Step 2: Query Overpass for nearby dining
    query = f"""
[out:json][timeout:25];
(
  node["amenity"="restaurant"](around:{radius_m},{lat},{lon});
  node["amenity"="cafe"](around:{radius_m},{lat},{lon});
  node["amenity"="fast_food"](around:{radius_m},{lat},{lon});
);
out body {limit * 2};
"""

    # Try each endpoint with a small delay between attempts
    elements = []
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            print(f"Trying {endpoint}...")
            resp = requests.post(endpoint, data={"data": query}, timeout=30)
            if resp.status_code == 200 and resp.text.strip():
                elements = resp.json().get("elements", [])
                print(f"Got {len(elements)} raw elements.")
                break
            else:
                print(f"Bad response ({resp.status_code}), trying next endpoint...")
                time.sleep(2)
        except Exception as e:
            print(f"Error with {endpoint}: {e}, trying next...")
            time.sleep(2)

    # Step 3: Parse results
    results = []
    for el in elements:
        tags = el.get("tags", {})
        if not tags.get("name"):
            continue
        results.append({
            "name": tags.get("name"),
            "type": tags.get("amenity"),
            "cuisine": tags.get("cuisine", "not listed"),
            "address": ", ".join(filter(None, [
                tags.get("addr:housenumber"),
                tags.get("addr:street"),
                tags.get("addr:city")
            ])) or "not listed",
            "hours": tags.get("opening_hours", "not listed"),
            "lat": el.get("lat"),
            "lon": el.get("lon"),
        })
        if len(results) >= limit:
            break

    return results


# if __name__ == "__main__":
#     parser = argparse.ArgumentParser()
#     parser.add_argument("location", type=str)
#     parser.add_argument("--radius", type=int, default=500)
#     parser.add_argument("--limit", type=int, default=5)
#     args = parser.parse_args()

#     results = search_dining(args.location, args.radius, args.limit)

#     if not results:
#         print("No dining options found.")
#     else:
#         for i, r in enumerate(results, 1):
#             print(f"\n{i}. {r['name']}")
#             print(f"   Type: {r['type']}")
#             print(f"   Cuisine: {r['cuisine']}")
#             print(f"   Address: {r['address']}")
#             print(f"   Hours: {r['hours']}")