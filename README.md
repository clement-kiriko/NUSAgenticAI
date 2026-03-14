# TripBuddy

Top-level workspace for the TripBuddy app.

## Overview
TripBuddy is a multi-agent travel planning system that creates and refines travel itineraries from user inputs:
- travel days
- total budget (SGD)
- country to visit
- travel start date
- dietary restrictions

The backend coordinates specialist agents for flights, locations, food, accommodations, budgeting, and final consolidation into a user-readable report.

## Key Capabilities
- Multi-agent orchestration with LangGraph
- Orchestration and message passing
- Dynamic tool discovery and Tool-governed backend runtime with MCP-compatible server
- Layered tool architecture (`tools/providers` + `tools/services`) for resilient provider fallback
- State management across planning rounds
- MCP stdio adapter exposing `initialize`, `tools/list`, and `tools/call`
- FastAPI API for session-based planning and streaming progress updates
- React frontend with intake form, live planning steps, chat refinements, and readable report output

## Multi-Agent Roles
- Flight Agent: proposes flight options and weather-aware travel strategy.
- Locations Agent: recommends attractions and neighborhood strategy.
- Food Agent: suggests meal planning based on budget and dietary restrictions.
- Accomodations Agent: recommends stay options with location/proximity considerations.
- Budget Agent: consolidates costs and checks if the plan fits user budget.
- Orchestrator/Consolidation Agent: coordinates round-robin execution and produces a final consolidated report.

Agents communicate through shared state and conversation history, and each specialist can use approved tools only (tool access control).

## Tool Integration
Tool integration includes:
- AviationStack via `FlightAPI` for flight data (`AVIATIONSTACK_API_KEY`; mock fallback if unavailable)
- WeatherStack via `WeatherAPI` for weather data (`WEATHERSTACK_API_KEY`; mock fallback if unavailable)
- Live food search via `food_search_live` in `tools/food_finder.py` (Nominatim + Overpass primary, Geoapify fallback)
- Geoapify-backed retrieval via destination tools in `tools/geoapify_tools.py` (`GEOAPIFY_API_KEY`; mock fallback if unavailable):
  - `food_catalog`
  - `places_search`
  - `route_estimate`
  - `place_signals`

Compatibility aliases (`search_dining`, `FoodAPI`, `WebSearchAPI`, `MapsAPI`, `ReviewsAPI`) are retained for older calls.

The system includes safe fallback behavior if external calls are unavailable.

## Iterative Refinement
- If the plan is over budget or a critical output field is missing, the system auto-optimizes by swapping to cheaper/complete alternatives.
- Optimization is capped at 3 rounds.
- User feedback is collected until satisfaction or max rounds reached.

## Structure
- `TripBuddy/backend/`: Python multi-agent planner (LangGraph), FastAPI API, MCP server
- `TripBuddy/frontend/`: React UI (single-page planner + help page)

## Setup Instructions
1. Download and unzip the code or clone the project.
2. Open terminal and go to the project folder.
3. Enter the project app folder:
```bash
cd TripBuddy
```
3. Install dependencies in frontend:
```bash
cd frontend
npm install
```
4. Install dependencies in backend:
```bash
cd ../backend
poetry install
```
5. In backend folder, create `.env` from `.env.example` and set:
- `OPENAI_API_KEY`
- `OPENAI_MODEL` (default: `gpt-5`)
- `GEOAPIFY_API_KEY`
- `AVIATIONSTACK_API_KEY`
- `WEATHERSTACK_API_KEY`
- `DEBUG` (`true`/`false`)
6. Run the app (Refer to Quick Start section) 

## Quick Start
1. Start backend:
```bash
cd TripBuddy/backend
poetry install
poetry run uvicorn api_server:app --reload --port 8000
```
2. Start Prometheus and Grafana:
```bash
cd TripBuddy/tools/prometheus
docker compose up -d
```
3. Start frontend:
```bash
cd TripBuddy/frontend
npm install
npm run dev
```
4. Open:
- Frontend: `http://localhost:5173`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000`

To access Grafana, use default login credentials.

## Session And Streaming Notes
- Planning runs continue on backend even if the frontend WebSocket disconnects mid-run.
- On reconnect, frontend requests a session snapshot and resumes live updates.
- If backend was restarted and session IDs are no longer valid, frontend now auto-clears stale local session state and prompts a fresh run.

## Documentation
- Backend details: `TripBuddy/backend/README.md`
- Frontend details: `TripBuddy/frontend/README.md`

## UI Screenshots
> Place image files in `TripBuddy/frontend/docs/images/`.

![TripBuddy Planner](./TripBuddy/frontend/docs/images/planner.png)
![TripBuddy Report Overview](./TripBuddy/frontend/docs/images/report-overview.png)
![TripBuddy Report Details](./TripBuddy/frontend/docs/images/report-details.png)
