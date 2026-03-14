# TripBuddy Frontend

React frontend for TripBuddy travel planning.

## Tech Stack
- ReactJS
- Vite
- React Router
- Browser WebSocket API
- Fetch API (REST integration with FastAPI backend)

## Features
- One-page travel query intake form
- Optional `/help` tutorial page
- Chat-style refinement after initial plan
- Live planning progress + chat via WebSocket
- Readable report sections (not raw JSON)
- Optimization pass indicator (`Optimization pass x/y`) during reruns
- Collapsible `Details` panel for condensed technical progress logs
- Stale session recovery: auto-reset local state when backend returns unknown/expired session

## Screenshots
> Place image files in `TripBuddy/frontend/docs/images/`.

### Planner
![TripBuddy Planner](./docs/images/planner.png)

### Report (Overview & Recommendations)
![TripBuddy Report Overview](./docs/images/report-overview.png)

### Report (Budget, Risks, Next Iteration)
![TripBuddy Report Details](./docs/images/report-details.png)

## Frontend Structure
- `src/App.jsx`: app routes only
- `src/pages/HomePage.jsx`: planner page composition
- `src/pages/HelpPage.jsx`: tutorial page
- `src/components/TravelForm.jsx`: intake form UI
- `src/components/PlannerChat.jsx`: chat panel and refinement controls
- `src/components/ProgressSteps.jsx`: step status cards
- `src/components/ReportPanel.jsx`: report renderer
- `src/hooks/usePlannerSession.js`: planner state orchestration and UI actions
- `src/services/plannerApi.js`: REST API calls
- `src/services/plannerSocket.js`: WebSocket transport helpers
- `src/utils/planner.js`: shared planner helpers/constants
- `src/assets/styles.css`: global app styles

## Requirements
- Node.js 18+
- Backend API running at `http://localhost:8000` (default)

## Setup
```bash
npm install
npm run dev
```

Open `http://localhost:5173`.

## Build
```bash
npm run build
npm run preview
```

## Production
The frontend now has:
- `npm run start` for non-dev preview mode
- `Dockerfile` for nginx-based production serving
- `nginx.conf` with same-origin proxying for `/api`, `/ws`, and `/metrics`

Production env template:
- `.env.production.example`

If you want the Docker frontend to use the same port as local Vite, set this in the root `.env.prod`:

```env
FRONTEND_PORT=5173
```

Container build from the repo root:

```bash
docker build -f TripBuddy/frontend/Dockerfile -t tripbuddy-frontend:latest .
```

Run the frontend container in production as part of the full stack:

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d frontend
```

Default production URL:
- Frontend: `http://localhost`

If `FRONTEND_PORT=5173`, the production frontend URL is `http://localhost:5173`.

Verify the frontend:

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml ps
docker compose --env-file .env.prod -f docker-compose.prod.yml logs frontend
```

Checks:
- Open the frontend in the browser.
- Submit a new trip request.
- Confirm progress updates appear.
- Confirm the final report renders.
- Confirm refinement/chat still works over WebSocket.

## Environment
Optional Vite env var:
- `VITE_API_BASE` (default: `http://localhost:8000`)
- `VITE_WS_BASE` (default: derived from `VITE_API_BASE`)

Example `.env`:
```bash
VITE_API_BASE=http://localhost:8000
VITE_WS_BASE=ws://localhost:8000
```

## API Endpoints Used
- `POST /api/session`
- `GET /api/session/{session_id}/snapshot`
- `POST /api/session/{session_id}/stop`
- `WS /ws/session/{session_id}`
- `POST /api/session/{session_id}/plan/stream` (fallback)
- `POST /api/session/{session_id}/plan` (fallback)
- `GET /api/health`
