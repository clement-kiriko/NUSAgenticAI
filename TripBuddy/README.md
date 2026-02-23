# TripBuddy Multi-Agent Travel Advisor (LangGraph)

## Implemented Backend Agents
- `Flight` agent (`FlightAPI`, `WeatherAPI`)
- `Locations` agent (`TouristAttractionAPI`)
- `Food` agent (`FoodAPI`)
- `Accomodations` agent (`AccomsAPI`)
- `Budget` agent (cost consolidation in SGD)
- `Orchestrator/Consolidation` agent

All specialist prompts include fairness + guardrails requirements.  
Default model is GPT-5 via `OPENAI_MODEL` (default: `gpt-5`).

## User Flow
1. Intake asks:
   - number of days
   - total trip budget in SGD
   - country to visit
   - travel start date
   - dietary restrictions
2. Orchestrator runs all specialist agents.
3. Consolidated report is shown to user.
4. If budget is exceeded, system auto-runs optimization rounds (max 3 total rounds) by swapping to cheaper options.
5. User can provide feedback; the workflow stops at satisfaction or when max rounds are reached.

## Architecture Mapping To Rubric
- Multiple agents with distinct personas:
  - Flight specialist, Locations specialist, Food specialist, Accomodations specialist, Budget analyst, and Orchestrator/Consolidation.
- Agent coordination:
  - `LangGraph` orchestrated round-robin flow per iteration:
    `orchestrator -> flight -> locations -> food -> accomodations -> budget -> consolidation -> feedback`.
  - If user is not satisfied, graph loops back to `orchestrator` for another round.
- Agent communication/message passing:
  - Shared `conversation` history in state.
  - Each agent appends its structured output and reads recent conversation context before producing next output.
- Tool integration:
  - Tools in `tools/travel_apis.py` are called by agents.
  - Retrieval-enabled tools include:
    - `TouristAttractionAPI` (Geoapify Places near destination when `GEOAPIFY_API_KEY` is set, otherwise mock fallback)
    - `FoodAPI` (Geoapify Places food categories near destination, otherwise mock fallback)
    - `AccomsAPI` (Geoapify Places accommodation categories near destination, otherwise mock fallback)
    - `WebSearchAPI` (Geoapify search/geocode when `GEOAPIFY_API_KEY` is set, otherwise mock fallback)
    - `MapsAPI` (Geoapify routing for proximity/travel-time context, otherwise mock fallback)
    - `ReviewsAPI` (Geoapify place signals; fallback mock when unavailable)
- Tool access control:
  - Centralized allowlist in `agents/orchestrator.py` (`TOOL_PERMISSIONS` + `call_tool`).
  - Unauthorized tool calls raise `PermissionError`.
- State management:
  - Shared typed state in `state.py` tracks user requirements, round number, tool call audit, specialist plans, conversation history, and final report.

## Run
```bash
poetry install
poetry run python main.py
```

Or with uv:
```bash
uv sync
uv run python main.py
```

## Sample Demo Input/Output
Sample intake input:

```text
Trip Advisor Intake
How many travel days? 4
Total trip budget (SGD)? 3000
Country to visit? japan
Travel start date (YYYY-MM-DD)? 2026-03-24
Dietary restrictions? (enter 'none' if not applicable): none
```

Sample consolidated output:

```text
=== Consolidated Trip Report ===
{
  "overview": "4 days in Japan (24\u201327 Mar 2026), balancing Tokyo convenience with a nature-focused side-trip to Gunma/Mount Akagi. Expect warm weather (24\u201331\u00b0C) with occasional showers. Plan prioritizes a nonstop round-trip flight for time reliability, a Tokyo base near JR hubs plus one night in Gunma to reduce transfers, and flexible activity choices (hike vs easy lakeside/shrine walks). Baseline, per-person costs in SGD total ~2,361.60, leaving strong headroom under the SGD 3,000 budget. Note: Intercity JR Tokyo\u2194Gunma may add ~SGD 100\u2013120 if not already included in the local estimate; even then, the trip remains within budget.",
  "recommendations": {
    "flights": {
      "selected": "SkyWays non-stop round-trip (Singapore \u2194 Japan, 24\u201327 Mar 2026)",
      "est_total_sgd": 1231.6,
      "why": "Non-stop minimizes missed-connection risk in showery spring weather and maximizes time on the ground.",
      "notes": "Assumes 15% taxes/fees and SGD 50 checked bag per segment. If prioritizing savings, a 1-stop option is ~SGD 161 cheaper but with higher delay risk."
    },
    "accommodations": [
      {
        "name": "Mid In Hotels (Kuramae, Taito, Tokyo)",
        "nights": 2,
        "dates": "Check-in 24 Mar, check-out 26 Mar",
        "area_reason": "1\u20132 stops to Ueno/Tokyo Station for fast JR/Shinkansen access to Gunma.",
        "est_total_sgd": 378,
        "inclusions": "Room only",
        "accessibility": "Elevators common; compact rooms. Request accessible room if needed.",
        "assumptions": "Late-March sakura demand may increase rates by ~20\u201340%."
      },
      {
        "name": "\u9752\u6728\u5225\u9928 (Aoki Bekkan), Gunma area",
        "nights": 1,
        "dates": "Check-in 26 Mar, check-out 27 Mar",
        "area_reason": "Closer to Akagi Shrine/lakeside viewpoints; reduces early transfers and adds weather buffer.",
        "est_total_sgd": 123,
        "inclusions": "Room only; ryokan meal plans extra.",
        "accessibility": "Traditional inns may have steps/futon/shared baths; confirm elevator/room type if needed."
      }
    ],
    "daily_plan": [
      {
        "day": "Tue 24 Mar",
        "intensity": "Light",
        "focus": "Arrive Tokyo; settle near JR hub (Ueno/Tokyo Station). Short city stroll.",
        "food": "Convenience-store breakfast; ramen/soba lunch; depachika/izakaya dinner.",
        "transport": "Airport rail to Tokyo base (avoid peak hours with luggage)."
      },
      {
        "day": "Wed 25 Mar",
        "intensity": "Moderate",
        "focus": "Gunma: Akagi Shrine, Sacred Spring, Onuma lakeside viewpoints.",
        "food": "Mountain teahouse lunch; Maebashi set-meal dinner.",
        "transport": "JR to Maebashi/Takasaki then local bus. Check last bus times."
      },
      {
        "day": "Thu 26 Mar",
        "intensity": "High (optional) or Light (alternative)",
        "focus": "Option A: Mount Akagi Kurohiyama Vista hike (weather-permitting). Option B: Maebashi riverwalk + Kitsutsuki-bashi.",
        "food": "Mountain lunch; Tokyo sushi/tempura dinner if returning to the city.",
        "transport": "Local buses/taxis if needed; be conservative with mountain weather windows."
      },
      {
        "day": "Fri 27 Mar",
        "intensity": "Light",
        "focus": "Tokyo buffer (shopping/back-up sights). Return flight.",        
        "food": "Eki-ben lunch; light airport meal pre-boarding.",
        "transport": "Rail to airport with time buffer."
      }
    ],
    "transport": {
      "intercity": "Choose JR TOKYO Wide Pass (~SGD 100/3 days) if doing multiple JR trips, otherwise point-to-point Tokyo\u2194Takasaki/Maebashi (~SGD 120 round-trip reserved). Coverage/prices can change\u2014verify before purchase.",
      "local_gunma": "Buses to Akagi area ~SGD 10\u201325 each way; taxis ~SGD 40\u201380 each way if buses are missed or infrequent.",
      "tokyo_transit": "Use IC card (Suica/PASMO). Most central trips are a few SGD each.",
      "airport_transfers": "Plan ~SGD 10\u201335 each way by rail depending on HND vs NRT/service.",
      "tips": "Set alarms for last bus departures; travel earlier on hike day to keep flexibility."
    },
    "food": {
      "plan_total_sgd": 314,
      "approach": "Casual, fast, and flexible options with vegetarian/seafood alternatives daily. No tipping. Occasional izakaya cover charge covered by 10% contingency.",
      "dietary_inclusivity": [
        "Vegetarian/seafood choices available daily.",
        "Halal-friendly approach: emphasize seafood/vegetarian; certification limited in mountain areas\u2014verify locally.",
        "Gluten caution: many sauces use soy (gluten). Consider rice/udon when needed."
      ]
    },
    "packing_and_prep": [
      "Light rain jacket, breathable quick-dry layers, sturdy walking shoes; optional trekking poles for hike.",
      "Cashless works widely in Tokyo; carry some cash in rural areas.",
      "Power adapter Type A/B; eSIM/roaming setup.",
      "Daypack, water bottle, light snacks for bus/hike windows."
    ],
    "inclusivity_accessibility": [
      "Swap hikes for flat lakeside paths and shrine precincts.",
      "Riverside promenades in Maebashi are generally step-free; confirm ramps/curb cuts locally.",
      "Prefer station/airport dining for step-free access if needed.",
      "Request accessible hotel room; verify ryokan facilities if mobility needs apply."
    ],
    "safety_tips": [
      "Check mountain weather/daylight; avoid wet/exposed sections during showers.",
      "Stick to marked trails; carry charged phone and offline maps.",
      "Mind last bus times in rural areas to avoid costly taxis.",
      "Hot foods are served very hot\u2014prevent burns.",
      "Travel insurance recommended."
    ],
    "savings_and_splurges": [
      "Save: Consider 1-stop flight (-~SGD 161) if delay risk acceptable.",       
      "Save: JR TOKYO Wide Pass if it suits your routing; otherwise buy point-to-point.",
      "Splurge: Ryokan dinner/breakfast add-on; luggage forwarding (SGD 25\u201335/suitcase) for a smoother split-stay."
    ]
  },
  "budget_summary": {
    "note": "All figures are per person in SGD. Lodging assumes solo traveler in one room; shared rooms may lower per-person lodging cost.",
    "baseline_breakdown": [
      {
        "item": "Flights (round-trip, nonstop, incl. est. bags/taxes)",
        "cost_sgd": 1231.6
      },
      {
        "item": "Lodging (2N Tokyo + 1N Gunma, taxes/fees est.)",
        "cost_sgd": 501
      },
      {
        "item": "Food & beverages (incl. 10% contingency, non-alcoholic)",        
        "cost_sgd": 314
      },
      {
        "item": "Local activities & local transport (Gunma/Tokyo)",
        "cost_sgd": 315
      }
    ],
    "baseline_subtotal_sgd": 2361.6,
    "not_included_yet": [
      {
        "item": "Intercity JR Tokyo\u2194Gunma (if not covered above)",
        "est_range_sgd": "100\u2013120",
        "notes": "JR TOKYO Wide Pass ~SGD 100/3 days or ~SGD 120 for reserved round-trip tickets."
      },
      {
        "item": "Airport transfers (round-trip)",
        "est_range_sgd": "20\u201370",
        "notes": "Varies by HND vs NRT and service level."
      },
      {
        "item": "Travel insurance",
        "est_range_sgd": "40\u201380",
        "notes": "Benefit levels vary; recommended."
      },
      {
        "item": "Luggage forwarding (optional, one-way)",
        "est_range_sgd": "25\u201335",
        "notes": "Per suitcase; useful for split-stay."
      },
      {
        "item": "Rural taxi fallback (per ride)",
        "est_range_sgd": "40\u201380",
        "notes": "Avoidable if buses are caught; keep as contingency."
      },
      {
        "item": "Possible sakura-season lodging surge",
        "est_range_sgd": "80\u2013160",
        "notes": "If not locked early; total increment for this itinerary."       
      }
    ],
    "scenarios": {
      "best_estimate_total_sgd": 2606.6,
      "best_estimate_buffer_sgd": 393.4,
      "conservative_total_sgd": 2826.6,
      "conservative_buffer_sgd": 173.4,
      "trip_budget_sgd": 3000
    },
    "assumptions": [
      "Exchange rates and pass coverage may change; figures are conservative where unknown.",
      "Local attractions listed with placeholder ticket fees; many riverside/shrine areas are free.",
      "Alcohol not included in food plan."
    ]
  },
  "risks": [
    {
      "risk": "Showers and variable mountain weather",
      "impact": "Reduced visibility on Mount Akagi; slippery trails; schedule changes.",
      "mitigation": "Keep Day 3 flexible; prioritize clear-weather window; choose lakeside/shrine alternatives; pack rain gear and proper footwear."
    },
    {
      "risk": "Sakura-season crowding and price volatility",
      "impact": "Higher hotel rates; sold-out trains or limited dining space in hotspots.",
      "mitigation": "Book refundable lodging early; reserve JR seats where possible; travel outside rush hours."
    },
    {
      "risk": "Rural bus frequency/last departures",
      "impact": "Stranded travelers; costly taxi (~SGD 40\u201380 each way).",    
      "mitigation": "Timebox hikes; set alarms for last buses; keep taxi numbers and cash/IC card handy."
    },
    {
      "risk": "Accessibility constraints at ryokan/mountain spots",
      "impact": "Stairs/tatami/shared baths may not suit all travelers.",
      "mitigation": "Confirm facilities in advance; opt for accessible rooms or stay Tokyo-based and focus on flat walks."
    },
    {
      "risk": "Allergens and dietary cross-contact (soy, sesame, fish dashi, gluten)",
      "impact": "Unexpected reactions or limited choices.",
      "mitigation": "Check labels and ask staff; favor rice dishes/plain broth; use translated allergy cards if needed."
    },
    {
      "risk": "Service changes or pass coverage updates",
      "impact": "Unexpected fare differences or route changes.",
      "mitigation": "Verify JR Pass coverage and timetables before purchase; keep a small fare buffer."
    }
  ],
  "next_iteration_focus": [
    "Confirm airport and flight times (HND vs NRT) to finalize airport transfers and Day 1/4 timing.",
    "Choose intercity option: JR TOKYO Wide Pass vs point-to-point tickets for Tokyo\u2194Gunma.",
    "Decide on split-stay (Tokyo 2N + Gunma 1N) vs single Tokyo base; if split, consider luggage forwarding.",
    "Lock refundable hotel rates soon to avoid sakura-season surges; confirm room type/accessibility needs.",
    "Pick Day 3 path: Kurohiyama hike vs Maebashi riverwalk, based on weather and desired intensity.",
    "Verify Akagi area bus timetables and last departures for your specific dates.",
    "Confirm any dietary preferences (even if none now) and any allergens to brief dining choices.",
    "Add travel insurance and note any pre-existing condition coverage needs (no sensitive medical details required).",
    "Outline airport rail route and seat reservations for JR segments where applicable.",
    "Optional: eSIM/roaming choice, cash vs card plan, and onsen/ryokan meal add-ons."
  ]
}

Are you satisfied with this plan? (yes/no): yes

Final Approved Report
{ ...full approved report printed... }
```

## Next Phases (Not Implemented Yet)
- Pipeline + cloud infra deployment
- Frontend UI
- External monitoring stack (Kafka, Grafana, Prometheus, GitHub Actions, LangFuse, Promptfoo, LangChain traces)
- MCP server integration for internal tools/data access
