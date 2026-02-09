TRIP_DATABASE = [
    {"country": "Japan", "city": "Tokyo", "duration_days": 5, "estimated_cost": 1800,
     "theme": "City & Culture", "highlights": ["Shibuya", "Asakusa", "Skytree"]},
    {"country": "Japan", "city": "Kyoto", "duration_days": 5, "estimated_cost": 1600,
     "theme": "Cultural & Nature", "highlights": ["Gion", "Kinkaku-ji", "Bamboo Forest"]},
    {"country": "Thailand", "city": "Bangkok", "duration_days": 5, "estimated_cost": 1200,
     "theme": "Food & Shopping", "highlights": ["Chatuchak", "Wat Pho", "Floating Market"]},
    {"country": "Singapore", "city": "Singapore", "duration_days": 5, "estimated_cost": 1500,
     "theme": "Modern & Family", "highlights": ["Sentosa", "Marina Bay Sands", "Gardens by the Bay"]}
]

def trip_data_tool(state: dict) -> dict:
    """Simple static filter based on user keywords & loose budget check."""
    q = state.get("user_input", "").lower()
    results = []

    for t in TRIP_DATABASE:
        if t["country"].lower() in q or t["city"].lower() in q:
            if ("under" in q or "budget" in q):
                if t["estimated_cost"] <= 3000:
                    results.append(t)
            else:
                results.append(t)

    if not results:
        results = TRIP_DATABASE[:2]

    state["trip_options"] = results
    print(f"🧭 TripDatabaseTool → {len(results)} matching trips found.")
    return state
