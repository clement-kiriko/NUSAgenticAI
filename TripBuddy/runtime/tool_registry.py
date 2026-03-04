from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Set

from tools import (
    accomodation_api,
    flight_api,
    food_api,
    maps_api,
    reviews_api,
    tourist_attraction_api,
    weather_api,
    web_search_api,
)
from tools.food_finder import search_dining


@dataclass(frozen=True)
class ToolSpec:
    name: str
    handler: Callable[..., Any]
    description: str
    capabilities: Set[str] = field(default_factory=set)
    allowed_agents: Set[str] = field(default_factory=set)
    llm_schema: Dict[str, Any] | None = None


def build_tool_registry() -> Dict[str, ToolSpec]:
    return {
        "FlightAPI": ToolSpec(
            name="FlightAPI",
            handler=flight_api,
            description="Fetch flight options.",
            capabilities={"flight_search"},
            allowed_agents={"flight_agent"},
        ),
        "WeatherAPI": ToolSpec(
            name="WeatherAPI",
            handler=weather_api,
            description="Fetch destination weather.",
            capabilities={"weather_current"},
            allowed_agents={"flight_agent"},
        ),
        "TouristAttractionAPI": ToolSpec(
            name="TouristAttractionAPI",
            handler=tourist_attraction_api,
            description="Find attractions near destination.",
            capabilities={"attraction_search"},
            allowed_agents={"locations_agent"},
        ),
        "FoodAPI": ToolSpec(
            name="FoodAPI",
            handler=food_api,
            description="Find food spots near destination.",
            capabilities={"food_catalog"},
            allowed_agents={"food_agent"},
        ),
        "AccomsAPI": ToolSpec(
            name="AccomsAPI",
            handler=accomodation_api,
            description="Find accommodations near destination.",
            capabilities={"accommodation_search"},
            allowed_agents={"accomodations_agent"},
        ),
        "WebSearchAPI": ToolSpec(
            name="WebSearchAPI",
            handler=web_search_api,
            description="Search destination places/geocoding signals.",
            capabilities={"geo_search"},
            allowed_agents={"locations_agent", "food_agent", "accomodations_agent"},
        ),
        "MapsAPI": ToolSpec(
            name="MapsAPI",
            handler=maps_api,
            description="Get route/proximity travel-time context.",
            capabilities={"route_estimate"},
            allowed_agents={"locations_agent", "accomodations_agent"},
        ),
        "ReviewsAPI": ToolSpec(
            name="ReviewsAPI",
            handler=reviews_api,
            description="Get place signals/review proxies.",
            capabilities={"place_signals"},
            allowed_agents={"locations_agent", "food_agent", "accomodations_agent"},
        ),
        "search_dining": ToolSpec(
            name="search_dining",
            handler=search_dining,
            description="Search nearby dining options from OSM Nominatim + Overpass.",
            capabilities={"food_live_search"},
            allowed_agents={"food_agent"},
            llm_schema={
                "type": "function",
                "function": {
                    "name": "search_dining",
                    "description": "Search for real nearby dining options given a location.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "The location to search near, e.g. 'Orchard Road, Singapore'",
                            },
                            "radius_m": {
                                "type": "integer",
                                "description": "Search radius in metres (default 500)",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Max number of results to return (default 5)",
                            },
                        },
                        "required": ["location"],
                    },
                },
            },
        ),
    }


def serialize_tool_catalog(registry: Dict[str, ToolSpec], agent_name: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for spec in registry.values():
        if agent_name in spec.allowed_agents:
            rows.append(
                {
                    "name": spec.name,
                    "description": spec.description,
                    "capabilities": sorted(spec.capabilities),
                }
            )
    return rows
