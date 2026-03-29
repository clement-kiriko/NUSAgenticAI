import os
import logging

from tools.providers import geoapify_geocode, geoapify_places, nominatim_geocode, overpass_dining

logger = logging.getLogger(__name__)


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
    logger.info("Food live search started location=%s radius_m=%s limit=%s", location, radius_m, limit)
    try:
        geo = nominatim_geocode(location)
    except Exception:
        logger.exception("Food live search Nominatim geocode failed location=%s", location)
        return []
    if not geo:
        logger.warning("Food live search geocode failed location=%s", location)
        return []

    lat, lon = geo["lat"], geo["lon"]
    logger.info("Food live search geocoded location=%s lat=%s lon=%s", location, lat, lon)
    try:
        elements = overpass_dining(lat=lat, lon=lon, radius_m=radius_m, limit=limit)
    except Exception:
        logger.exception("Food live search Overpass failed location=%s", location)
        elements = []
    overpass_results = _parse_overpass(elements, limit=limit)
    if overpass_results:
        logger.info("Food live search completed via overpass location=%s results=%s", location, len(overpass_results))
        return overpass_results

    logger.warning("Food live search falling back to Geoapify location=%s", location)
    key = os.getenv("GEOAPIFY_API_KEY", "").strip()
    if not key:
        logger.warning("Food live search Geoapify fallback unavailable location=%s reason=missing key", location)
        return []

    try:
        geoapify_geo = geoapify_geocode(location, api_key=key)
        if not geoapify_geo:
            logger.warning("Food live search Geoapify geocode failed location=%s", location)
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
        logger.info("Food live search completed via Geoapify fallback location=%s results=%s", location, len(results))
        return results
    except Exception:
        logger.exception("Food live search Geoapify fallback failed location=%s", location)
        return []
