import asyncio
import queue
import threading
import time
import uuid
from typing import Any, Dict

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field

from metrics import AGENT_LATENCY, HTTP_REQUESTS_TOTAL, HTTP_REQUEST_DURATION
from planner import as_sse_event, build_initial_state, run_planner_stream

load_dotenv(override=True)

app = FastAPI(title="TripBuddy API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def record_http_metrics(request, call_next):
    started_at = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - started_at
    route = request.scope.get("route")
    path = getattr(route, "path", request.url.path)
    status_code = str(response.status_code)
    method = request.method
    HTTP_REQUESTS_TOTAL.labels(method=method, path=path, status_code=status_code).inc()
    HTTP_REQUEST_DURATION.labels(method=method, path=path, status_code=status_code).observe(duration)
    return response

SESSIONS: Dict[str, Dict[str, Any]] = {}
SESSION_RUNTIME: Dict[str, Dict[str, Any]] = {}


def _new_runtime() -> Dict[str, Any]:
    return {
        "events": [],
        "running": False,
        "abort_requested": False,
        "lock": threading.Lock(),
    }


def _ensure_runtime(session_id: str) -> Dict[str, Any]:
    runtime = SESSION_RUNTIME.get(session_id)
    if runtime is None:
        runtime = _new_runtime()
        SESSION_RUNTIME[session_id] = runtime
    return runtime


def _append_runtime_event(session_id: str, event: Dict[str, Any]) -> None:
    runtime = _ensure_runtime(session_id)
    lock = runtime["lock"]
    with lock:
        runtime.setdefault("events", []).append(event)
        # Keep bounded history to prevent unbounded memory growth.
        if len(runtime["events"]) > 1200:
            runtime["events"] = runtime["events"][-1200:]


def _runtime_snapshot(session_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
    runtime = _ensure_runtime(session_id)
    lock = runtime["lock"]
    with lock:
        events = list(runtime.get("events", []))
        running = bool(runtime.get("running", False))
    return {
        "session_id": session_id,
        "events": events,
        "running": running,
        "report": state.get("final_report", state.get("report")),
    }


def _start_planner_run(session_id: str, feedback: str, mode: str) -> tuple[bool, str]:
    state = SESSIONS.get(session_id)
    if state is None:
        return False, "Unknown session_id"
    runtime = _ensure_runtime(session_id)
    lock = runtime["lock"]

    with lock:
        if runtime.get("running", False):
            return False, "A planning run is already in progress."
        runtime["running"] = True
        runtime["abort_requested"] = False
        state["_abort_run"] = False

    # Route in-agent/tool progress events into shared runtime history.
    state["_emit_event"] = lambda event: _append_runtime_event(session_id, event)
    _append_runtime_event(session_id, {"type": "run_started", "mode": mode})

    def runner() -> None:
        try:
            for event in run_planner_stream(state, feedback=feedback):
                _append_runtime_event(session_id, event)
        except Exception as exc:  # noqa: BLE001
            _append_runtime_event(session_id, {"type": "error", "message": str(exc)})
        finally:
            with lock:
                runtime["running"] = False
            _append_runtime_event(session_id, {"type": "run_finished", "mode": mode})

    threading.Thread(target=runner, daemon=True).start()
    return True, "started"


class PlanRequest(BaseModel):
    days: int = Field(gt=0)
    budget_sgd: float = Field(gt=0)
    country: str = Field(min_length=1)
    start_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    dietary_restrictions: str = "none"


class RefineRequest(BaseModel):
    message: str = ""


@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
def metrics() -> StreamingResponse:
    return StreamingResponse(iter([generate_latest()]), media_type=CONTENT_TYPE_LATEST)


@app.post("/api/session")
def create_session(req: PlanRequest) -> Dict[str, str]:
    session_id = str(uuid.uuid4())
    SESSIONS[session_id] = build_initial_state(req.model_dump())
    SESSION_RUNTIME[session_id] = _new_runtime()
    return {"session_id": session_id}


@app.get("/api/session/{session_id}/snapshot")
def session_snapshot(session_id: str) -> Dict[str, Any]:
    state = SESSIONS.get(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Unknown session_id")
    return _runtime_snapshot(session_id, state)


@app.post("/api/session/{session_id}/plan")
def plan_once(session_id: str, body: RefineRequest | None = None) -> JSONResponse:
    state = SESSIONS.get(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Unknown session_id")

    feedback = body.message if body else ""
    run_started_at = time.perf_counter()
    events = list(run_planner_stream(state, feedback=feedback))
    AGENT_LATENCY.labels(agent_name="planner_run").observe(time.perf_counter() - run_started_at)
    final = events[-1] if events else {}
    return JSONResponse({"events": events, "result": final})


@app.post("/api/session/{session_id}/stop")
def stop_session_run(session_id: str) -> Dict[str, Any]:
    state = SESSIONS.get(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Unknown session_id")

    state["_abort_run"] = True
    runtime = _ensure_runtime(session_id)
    lock = runtime["lock"]
    with lock:
        runtime["abort_requested"] = True
    return {"ok": True, "session_id": session_id, "message": "Stop requested."}


@app.post("/api/session/{session_id}/plan/stream")
async def plan_stream(session_id: str, body: RefineRequest | None = None) -> StreamingResponse:
    state = SESSIONS.get(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Unknown session_id")

    feedback = body.message if body else ""

    event_queue: queue.Queue[Dict[str, Any]] = queue.Queue()

    def emit(event: Dict[str, Any]) -> None:
        event_queue.put(event)

    state["_emit_event"] = emit

    def runner() -> None:
        try:
            for event in run_planner_stream(state, feedback=feedback):
                event_queue.put(event)
        except Exception as exc:  # noqa: BLE001
            event_queue.put({"type": "error", "message": str(exc)})
        finally:
            event_queue.put({"type": "__stream_done__"})

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()

    async def event_gen():
        done = False
        while not done:
            try:
                event = event_queue.get(timeout=0.2)
            except queue.Empty:
                await asyncio.sleep(0.05)
                continue

            event_type = str(event.get("type", "update"))
            if event_type == "__stream_done__":
                done = True
                continue
            yield as_sse_event(event_type, event)
            await asyncio.sleep(0)

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@app.websocket("/ws/session/{session_id}")
async def session_websocket(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()

    async def safe_send(payload: Dict[str, Any]) -> bool:
        try:
            await websocket.send_json(payload)
            return True
        except (WebSocketDisconnect, RuntimeError):
            return False
        except Exception:
            return False

    state = SESSIONS.get(session_id)
    runtime = _ensure_runtime(session_id)
    tail_task: asyncio.Task | None = None

    async def start_tail_stream() -> None:
        nonlocal tail_task
        if runtime is None:
            return
        if tail_task and not tail_task.done():
            tail_task.cancel()

        lock = runtime["lock"]
        with lock:
            start_index = len(runtime.get("events", []))

        async def _tail(from_index: int) -> None:
            idx = from_index
            while True:
                with lock:
                    rows = list(runtime.get("events", []))
                    running = bool(runtime.get("running", False))
                while idx < len(rows):
                    ok = await safe_send(rows[idx])
                    if not ok:
                        return
                    idx += 1
                await asyncio.sleep(0.25)
                if not running and idx >= len(rows):
                    return

        with lock:
            running_now = bool(runtime.get("running", False))
        if running_now:
            tail_task = asyncio.create_task(_tail(start_index))

    if state is None:
        await safe_send({"type": "error", "message": "Unknown session_id"})
        await websocket.close(code=4404)
        return

    sent = await safe_send({"type": "snapshot", **_runtime_snapshot(session_id, state)})
    if not sent:
        return
    await start_tail_stream()

    try:
        while True:
            payload = await websocket.receive_json()
            action = str(payload.get("action", "")).strip().lower()
            message = str(payload.get("message", "")).strip()
            if action == "sync":
                ok = await safe_send({"type": "snapshot", **_runtime_snapshot(session_id, state)})
                if not ok:
                    return
                await start_tail_stream()
                continue

            if action not in {"start", "refine"}:
                ok = await safe_send({"type": "error", "message": "Invalid action. Use 'start' or 'refine'."})
                if not ok:
                    return
                continue

            started, reason = _start_planner_run(session_id, feedback=message, mode=action)
            if not started:
                ok = await safe_send({"type": "error", "message": reason})
                if not ok:
                    return
                continue

            ok = await safe_send({"type": "ack", "message": "Run started."})
            if not ok:
                return
            await start_tail_stream()
    except WebSocketDisconnect:
        if tail_task and not tail_task.done():
            tail_task.cancel()
        return
    except Exception as exc:  # noqa: BLE001
        if tail_task and not tail_task.done():
            tail_task.cancel()
        await safe_send({"type": "error", "message": str(exc)})
