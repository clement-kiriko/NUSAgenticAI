from tools.services import search_food_live


def food_search_live(location: str, radius_m: int = 500, limit: int = 5) -> list[dict]:
    return search_food_live(location=location, radius_m=radius_m, limit=limit)


def fallback_food_search_live(location: str, radius_m: int = 500, limit: int = 5) -> list[dict]:
    return []


# Backward-compat alias for older calls.
def search_dining(location: str, radius_m: int = 500, limit: int = 5) -> list[dict]:
    return food_search_live(location=location, radius_m=radius_m, limit=limit)
