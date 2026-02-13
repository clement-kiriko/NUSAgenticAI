Overview of the Solution
Overview of the Solution

The Trip Planner Council is a multi-agent travel planning system that collaborates to generate a complete trip plan based on user inputs (travel days, budget in SGD, country, start date, and dietary restrictions).

The system currently includes six coordinated agents:
- Flight Agent: proposes flight options and weather-aware travel strategy.
- Locations Agent: recommends attractions and neighborhood strategy.
- Food Agent: suggests meal planning based on budget and dietary restrictions.
- Accomodations Agent: recommends stay options with location/proximity considerations.
- Budget Agent: consolidates costs and checks if the plan fits user budget.
- Orchestrator/Consolidation Agent: coordinates round-robin execution and produces a final consolidated report.

Agents communicate through shared state and conversation history, and each specialist can use approved tools only (tool access control).  
Tool integration includes Geoapify-backed retrieval (search, routing/proximity, place signals) with safe fallback behavior if external calls are unavailable.

The planner supports iterative refinement:
- If the plan is over budget, the system auto-optimizes by swapping to cheaper alternatives.
- Optimization is capped at 3 rounds.
- User feedback is collected until satisfaction or max rounds reached.

This demonstrates:
- multi-agent architecture and specialization
- orchestration and message passing
- tool integration and permission controls
- state management across planning rounds

Set up instructions

1. Download and unzip the code or git clone the project.
2. Open terminal and go to the project folder.
3. Go into `TripBuddy`:
   - `cd TripBuddy`
4. Install dependencies:
   - `poetry install`
5. Create `.env` from `.env.example` and set:
   - `OPENAI_API_KEY`
   - `OPENAI_MODEL` (default: `gpt-5`)
   - `GEOAPIFY_API_KEY`
   - `DEBUG` (`true`/`false`)
6. Run:
   - `poetry run python main.py`