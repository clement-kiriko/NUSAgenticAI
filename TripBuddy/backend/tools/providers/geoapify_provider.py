import requests


def geoapify_geocode(location: str, api_key: str, timeout: int = 10) -> dict | None:
    resp = requests.get(
        "https://api.geoapify.com/v1/geocode/search",
        params={"text": location, "limit": 1, "apiKey": api_key},
        timeout=timeout,
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
    resp.raise_for_status()
    return resp.json().get("features", [])
