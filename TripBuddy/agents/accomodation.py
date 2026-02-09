def scheduler(state):
    print(f"🧭 Scheduler Agent Running")
    plan = ("Itinerary: Day 1–3 city highlights, Day 4–6 culture & history, "
            "Day 7–9 leisure/shopping/food, Day 10 departure.")
    print(f"🗓️ Scheduler Expert: {plan}")
    state["conversation"].append(("scheduler_expert", plan))
    state["schedule_done"] = True
    return state
