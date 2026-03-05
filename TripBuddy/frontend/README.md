# TripBuddy Frontend

React frontend for TripBuddy travel planning.

## Features
- One-page travel query intake form
- Optional `/help` tutorial page
- Chat-style refinement after initial plan
- Live planning progress + chat via WebSocket
- Readable report sections (not raw JSON)
- Optimization pass indicator (`Optimization pass x/y`) during reruns
- Collapsible `Details` panel for condensed technical progress logs
- Stale session recovery: auto-reset local state when backend returns unknown/expired session

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
