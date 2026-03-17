AGENT_TOOL_POLICY = {
    "flight_agent": {"flight_search", "weather_current"},
    "budget_agent": set(),
    "accomodations_agent": {
        "accommodation_search",
        "geo_search",
        "route_estimate",
        "place_signals" 
    },
    "locations_agent": {"attraction_search", "geo_search", "route_estimate", "place_signals"},
    "orchestrator_agent": set(),
    "food_agent": {"food_catalog", "food_live_search", "geo_search", "place_signals"}
}