import asyncio
import logging
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

from logging_setup import configure_logging
from monitoring import record_http_metrics, record_monitoring_event, timed_agent_call
from planner import as_sse_event, build_initial_state, run_planner_stream
from policy_engine import get_audit_id, get_run_id, start_new_run

load_dotenv(override=True)
configure_logging()

logger = logging.getLogger(__name__)

app = FastAPI(title="TripBuddy API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def prometheus_http_metrics(request, call_next):
    return await record_http_metrics(request, call_next)

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
        "run_id": get_run_id(state),
        "report": state.get("final_report", state.get("report")),
    }


def _audit_payload(session_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
    runtime = _ensure_runtime(session_id)
    lock = runtime["lock"]
    with lock:
        events = list(runtime.get("events", []))
        running = bool(runtime.get("running", False))
    return {
        "session_id": session_id,
        "audit_id": get_audit_id(state),
        "run_id": get_run_id(state),
        "running": running,
        "events": events,
        "tool_calls": state.get("tool_calls", []),
        "decision_trace_full": state.get("decision_trace", []),
        "policy_evaluation": state.get("policy_evaluation", {}),
        "specialist_plans": {
            "flight_plan": state.get("flight_plan", {}),
            "locations_plan": state.get("locations_plan", {}),
            "food_plan": state.get("food_plan", {}),
            "accomodations_plan": state.get("accomodations_plan", {}),
            "budget_plan": state.get("budget_plan", {}),
        },
        "final_report": state.get("final_report", state.get("report")),
        "governance_metadata": state.get("governance_metadata", {}),
        "run_history": state.get("governance_metadata", {}).get("run_history", []),
    }


def _start_planner_run(session_id: str, feedback: str, mode: str) -> tuple[bool, str]:
    state = SESSIONS.get(session_id)
    if state is None:
        logger.warning("Planner run requested for unknown session session_id=%s mode=%s", session_id, mode)
        return False, "Unknown session_id"
    runtime = _ensure_runtime(session_id)
    lock = runtime["lock"]

    with lock:
        if runtime.get("running", False):
            logger.warning("Planner run rejected because one is already active session_id=%s mode=%s", session_id, mode)
            return False, "A planning run is already in progress."
        runtime["running"] = True
        runtime["abort_requested"] = False
        state["_abort_run"] = False
    run_id = start_new_run(state, mode)

    # Route in-agent/tool progress events into shared runtime history.
    state["_emit_event"] = lambda event: _append_runtime_event(session_id, event)
    _append_runtime_event(session_id, {"type": "run_started", "mode": mode, "run_id": run_id})
    logger.info("Planner run accepted session_id=%s mode=%s", session_id, mode, extra={"audit_id": get_audit_id(state), "run_id": run_id})
    record_monitoring_event("session_run_started", audit_id=get_audit_id(state), run_id=run_id, session_id=session_id, mode=mode)

    def runner() -> None:
        try:
            for event in run_planner_stream(state, feedback=feedback):
                _append_runtime_event(session_id, event)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Planner background run failed session_id=%s mode=%s", session_id, mode, extra={"audit_id": get_audit_id(state), "run_id": get_run_id(state)})
            _append_runtime_event(session_id, {"type": "error", "message": str(exc)})
        finally:
            with lock:
                runtime["running"] = False
            _append_runtime_event(session_id, {"type": "run_finished", "mode": mode, "run_id": get_run_id(state)})
            logger.info("Planner run finished session_id=%s mode=%s", session_id, mode, extra={"audit_id": get_audit_id(state), "run_id": get_run_id(state)})
            record_monitoring_event("session_run_finished", audit_id=get_audit_id(state), run_id=get_run_id(state), session_id=session_id, mode=mode)

    threading.Thread(target=runner, daemon=True).start()
    return True, "started"


class PlanRequest(BaseModel):
    days: int = Field(gt=0)
    budget_sgd: float = Field(gt=0)
    country: str = Field(min_length=1)
    city: str = ""
    start_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    dietary_restrictions: str = "none"


class RefineRequest(BaseModel):
    message: str = ""


@app.get("/api/health")
def health() -> Dict[str, str]:
    logger.info("Health check requested.")
    return {"status": "ok"}


@app.get("/metrics")
def metrics() -> StreamingResponse:
    return StreamingResponse(iter([generate_latest()]), media_type=CONTENT_TYPE_LATEST)


@app.post("/api/session")
def create_session(req: PlanRequest) -> Dict[str, str]:
    session_id = str(uuid.uuid4())
    SESSIONS[session_id] = build_initial_state(req.model_dump())
    SESSION_RUNTIME[session_id] = _new_runtime()
    audit_id = get_audit_id(SESSIONS[session_id])
    logger.info(
        "Session created session_id=%s country=%s city=%s days=%s",
        session_id,
        req.country,
        req.city,
        req.days,
        extra={"audit_id": audit_id},
    )
    record_monitoring_event(
        "session_created",
        audit_id=audit_id,
        session_id=session_id,
        country=req.country,
        city=req.city,
        days=req.days,
    )
    return {"session_id": session_id}


@app.get("/api/session/{session_id}/snapshot")
def session_snapshot(session_id: str) -> Dict[str, Any]:
    state = SESSIONS.get(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Unknown session_id")
    return _runtime_snapshot(session_id, state)


@app.get("/api/session/{session_id}/audit")
def session_audit(session_id: str) -> Dict[str, Any]:
    state = SESSIONS.get(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Unknown session_id")
    logger.info("Audit export requested session_id=%s", session_id, extra={"audit_id": get_audit_id(state), "run_id": get_run_id(state)})
    record_monitoring_event("session_audit_exported", audit_id=get_audit_id(state), run_id=get_run_id(state), session_id=session_id)
    return _audit_payload(session_id, state)


@app.post("/api/session/{session_id}/plan")
def plan_once(session_id: str, body: RefineRequest | None = None) -> JSONResponse:
    state = SESSIONS.get(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Unknown session_id")

    feedback = body.message if body else ""
    logger.info(
        "Plan once requested session_id=%s feedback_present=%s",
        session_id,
        bool(feedback.strip()),
        extra={"audit_id": get_audit_id(state), "run_id": get_run_id(state)},
    )
    events = timed_agent_call("planner_run", list, run_planner_stream(state, feedback=feedback))
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
    logger.info("Stop requested session_id=%s", session_id, extra={"audit_id": get_audit_id(state), "run_id": get_run_id(state)})
    record_monitoring_event("session_stop_requested", audit_id=get_audit_id(state), run_id=get_run_id(state), session_id=session_id)
    return {"ok": True, "session_id": session_id, "message": "Stop requested."}


@app.post("/api/session/{session_id}/plan/stream")
async def plan_stream(session_id: str, body: RefineRequest | None = None) -> StreamingResponse:
    state = SESSIONS.get(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Unknown session_id")

    feedback = body.message if body else ""
    logger.info(
        "SSE plan stream requested session_id=%s feedback_present=%s",
        session_id,
        bool(feedback.strip()),
        extra={"audit_id": get_audit_id(state), "run_id": get_run_id(state)},
    )

    event_queue: queue.Queue[Dict[str, Any]] = queue.Queue()

    def emit(event: Dict[str, Any]) -> None:
        event_queue.put(event)

    state["_emit_event"] = emit

    def runner() -> None:
        try:
            for event in run_planner_stream(state, feedback=feedback):
                event_queue.put(event)
        except Exception as exc:  # noqa: BLE001
            logger.exception("SSE planner stream failed session_id=%s", session_id, extra={"audit_id": get_audit_id(state), "run_id": get_run_id(state)})
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
    logger.info("WebSocket connected session_id=%s", session_id)

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
        logger.warning("WebSocket rejected for unknown session session_id=%s", session_id)
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
        logger.info("WebSocket disconnected session_id=%s", session_id, extra={"audit_id": get_audit_id(state), "run_id": get_run_id(state)})
        return
    except Exception as exc:  # noqa: BLE001
        if tail_task and not tail_task.done():
            tail_task.cancel()
        logger.exception("WebSocket session failed session_id=%s", session_id, extra={"audit_id": get_audit_id(state), "run_id": get_run_id(state)})
        await safe_send({"type": "error", "message": str(exc)})
