import os

from tools.providers import geoapify_geocode, geoapify_places, nominatim_geocode, overpass_dining


def _parse_overpass(elements: list[dict], limit: int) -> list[dict]:
    results: list[dict] = []
    for el in elements:
        tags = el.get("tags", {})
        if not tags.get("name"):
            continue
        results.append(
            {
                "name": tags.get("name"),
                "type": tags.get("amenity"),
                "cuisine": tags.get("cuisine", "not listed"),
                "address": ", ".join(
                    filter(None, [tags.get("addr:housenumber"), tags.get("addr:street"), tags.get("addr:city")])
                )
                or "not listed",
                "hours": tags.get("opening_hours", "not listed"),
                "lat": el.get("lat"),
                "lon": el.get("lon"),
                "source": "overpass",
            }
        )
        if len(results) >= limit:
            break
    return results


def _parse_geoapify(features: list[dict], limit: int) -> list[dict]:
    results: list[dict] = []
    for feature in features:
        props = feature.get("properties", {})
        name = props.get("name")
        if not name:
            continue
        categories = props.get("categories", [])
        results.append(
            {
                "name": name,
                "type": categories[0].split(".")[-1] if categories else "restaurant",
                "cuisine": props.get("catering", "not listed"),
                "address": props.get("formatted", "not listed"),
                "hours": props.get("opening_hours", "not listed"),
                "lat": props.get("lat"),
                "lon": props.get("lon"),
                "source": "geoapify_fallback",
            }
        )
        if len(results) >= limit:
            break
    return results


def search_food_live(location: str, radius_m: int = 500, limit: int = 5) -> list[dict]:
    geo = nominatim_geocode(location)
    if not geo:
        raise ValueError(f"Could not find location: {location}")

    lat, lon = geo["lat"], geo["lon"]
    print(f"Geocoded '{location}' -> lat={lat}, lon={lon}")
    elements = overpass_dining(lat=lat, lon=lon, radius_m=radius_m, limit=limit)
    overpass_results = _parse_overpass(elements, limit=limit)
    if overpass_results:
        return overpass_results

    print("No usable Overpass results. Falling back to Geoapify...")
    key = os.getenv("GEOAPIFY_API_KEY", "").strip()
    if not key:
        print("Geoapify fallback unavailable: GEOAPIFY_API_KEY is not set.")
        return []

    try:
        geoapify_geo = geoapify_geocode(location, api_key=key)
        if not geoapify_geo:
            print(f"Geoapify fallback geocode failed for '{location}'.")
            return []
        features = geoapify_places(
            geoapify_geo["lon"],
            geoapify_geo["lat"],
            categories="catering.restaurant,catering.fast_food,catering.cafe",
            api_key=key,
            limit=max(3, limit * 2),
            radius_m=max(5000, radius_m * 8),
        )
        results = _parse_geoapify(features, limit=limit)
        print(f"Geoapify fallback returned {len(results)} result(s).")
        return results
    except Exception as exc:
        print(f"Geoapify fallback failed: {exc}")
        return []
