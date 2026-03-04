# Overview of the Solution

The Trip Planner Council is a multi-agent travel planning system that collaborates to generate a complete trip plan based on user inputs (travel days, budget in SGD, country, start date, and dietary restrictions).

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
- OpenStreetMap via `search_dining` in `tools/food_finder.py` (Nominatim + Overpass; no API key required, subject to public endpoint limits)
- Geoapify-backed retrieval via destination tools in `tools/geoapify_tools.py` (`GEOAPIFY_API_KEY`; mock fallback if unavailable):
  - search
  - routing/proximity
  - place signals

The system includes safe fallback behavior if external calls are unavailable.

## Iterative Refinement
- If the plan is over budget, the system auto-optimizes by swapping to cheaper alternatives.
- Optimization is capped at 3 rounds.
- User feedback is collected until satisfaction or max rounds reached.

## What This Demonstrates
- multi-agent architecture and specialization
- orchestration and message passing
- MCP-style layers: LLM Router, Tool Registry, Tool Gateway
- dynamic tool discovery and governance controls
- state management across planning rounds
- MCP stdio adapter exposing `initialize`, `tools/list`, and `tools/call`

## Setup Instructions
1. Download and unzip the code or clone the project.
2. Open terminal and go to the project folder.
3. Enter the project app folder:
```bash
cd TripBuddy
```
4. Install dependencies:
```bash
poetry install
```
5. Create `.env` from `.env.example` and set:
- `OPENAI_API_KEY`
- `OPENAI_MODEL` (default: `gpt-5`)
- `GEOAPIFY_API_KEY`
- `AVIATIONSTACK_API_KEY`
- `WEATHERSTACK_API_KEY`
- `DEBUG` (`true`/`false`)
6. Run the app:
```bash
poetry run python main.py
```
7. Run MCP server (for external MCP clients):
```bash
poetry run python mcp_server.py
```
8. Test MCP quickly (PowerShell example):
```powershell
'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | poetry run python mcp_server.py
```
For full MCP usage/testing examples (`initialize`, `tools/list`, `tools/call`), see `TripBuddy/README.md` under `MCP Server (stdio)`.
