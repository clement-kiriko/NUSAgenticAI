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
How many travel days? 5
Total trip budget (SGD)? 4000
Country to visit? japan
Travel start date (YYYY-MM-DD)? 2026-11-25
Dietary restrictions? (enter 'none' if not applicable): none
```

Sample consolidated output:

```text
=== Consolidated Trip Report ===
{
  "overview": {
    "trip_window": {
      "days": 5,
      "start_date": "2026-11-25",
      "end_date": "2026-11-29",
      "location_preference": "Japan",
      "assumed_base_city": "Tokyo (chosen for convenience, density of sights, and connectivity)"
    },
    "headline_plan": "Nonstop round-trip flight, 4 nights in a mid-range Tokyo hotel (Ueno/Asakusa area), compact sightseeing clustered by neighborhood to cut transit time, casual local meals with a couple of sit-down dinners, and a flex day for weather or an optional day trip."
  },
  "recommendations": {
    "booking_actions": [
      "Flights: Book the SkyWays nonstop now if schedules and price (~SGD 1140 incl. bag/seat buffers) work for you.",
      "Hotel: Reserve Riverside Hotel (Ueno/Asakusa) for 4 nights (~SGD 609 est.).",
      "Observation deck: Pre-book a sunset timeslot (~SGD 40).",
      "Travel insurance: Purchase basic cover (~SGD 40-80).",
      "Connectivity: Arrange an eSIM/SIM (~SGD 10-25)."
    ]
  },
  "budget_summary": {
    "projected_total_sgd": 2168,
    "budget": {
      "total_budget_sgd": 4000,
      "within_budget": true,
      "buffer_remaining_sgd": 1832
    }
  },
  "risks": [
    {
      "risk": "Generic weather feed mismatch vs late-Nov Tokyo norms.",
      "mitigation": "Plan for 8-16C with showers; re-check city forecast 48-72 hours pre-departure."
    }
  ],
  "next_iteration_focus": [
    "City confirmation and preferred base.",
    "Airport selection (Narita vs Haneda).",
    "Pace/interests and optional experiences."
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
