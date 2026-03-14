import { useEffect, useMemo, useRef, useState } from "react";
import { createPlannerSession, fetchSessionSnapshot, stopPlannerSession } from "../services/plannerApi";
import { createPlannerSocket, sendPlannerSocketAction } from "../services/plannerSocket";
import { STEP_ORDER, eventToStatus, toTitle } from "../utils/planner";

const HOME_STATE_KEY = "tripbuddy_home_state_v1";

function loadSavedState() {
  try {
    const raw = sessionStorage.getItem(HOME_STATE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function usePlannerSession() {
  const savedState = loadSavedState();
  const [form, setForm] = useState(
    () =>
      savedState?.form || {
        days: 4,
        budget_sgd: 3000,
        country: "",
        start_date: "",
        dietary_restrictions: "none",
      },
  );
  const [sessionId, setSessionId] = useState(() => savedState?.sessionId || "");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [events, setEvents] = useState(() => savedState?.events || []);
  const [messages, setMessages] = useState(() => savedState?.messages || []);
  const [report, setReport] = useState(() => savedState?.report || null);
  const [chatInput, setChatInput] = useState("");
  const [socketReady, setSocketReady] = useState(false);
  const [showDetails, setShowDetails] = useState(false);
  const [currentStatus, setCurrentStatus] = useState(() => {
    const savedEvents = savedState?.events || [];
    const last = savedEvents.length ? savedEvents[savedEvents.length - 1].payload : null;
    return eventToStatus(last);
  });
  const hasStarted = Boolean(sessionId);
  const wsRef = useRef(null);
  const wsConnectPromiseRef = useRef(null);
  const reconnectTimerRef = useRef(null);
  const suppressReconnectRef = useRef(false);
  const pendingRefineRef = useRef(false);

  useEffect(() => {
    sessionStorage.setItem(HOME_STATE_KEY, JSON.stringify({ form, sessionId, events, messages, report }));
  }, [form, sessionId, events, messages, report]);

  useEffect(() => {
    if (!sessionId) return;
    syncFromSnapshot(sessionId)
      .then((ok) => {
        if (!ok) return;
        connectSessionSocket(sessionId, true).catch(() => {
          // silent reconnect attempt; explicit errors will show on next action
        });
      })
      .catch(() => {
        // silent restore attempt
      });
  }, []); // mount restore only

  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
      }
    };
  }, []);

  const stepStatus = useMemo(() => {
    const status = Object.fromEntries(STEP_ORDER.map((step) => [step, "idle"]));
    events.forEach((event) => {
      if (event.type === "step_started") status[event.payload.step] = "running";
      if (event.type === "step_completed") status[event.payload.step] = "done";
    });
    return status;
  }, [events]);

  const roundMeta = useMemo(() => {
    let round = 0;
    let maxRounds = 0;
    events.forEach((event) => {
      const payload = event.payload || {};
      const r = Number(payload.round || 0);
      const m = Number(payload.max_rounds || 0);
      if (r > 0) round = Math.max(round, r);
      if (m > 0) maxRounds = Math.max(maxRounds, m);
    });
    return { round, maxRounds };
  }, [events]);

  const passBadgeText = useMemo(() => {
    if (!loading || roundMeta.round <= 1 || roundMeta.maxRounds <= 1) return "";
    return `Optimization pass ${roundMeta.round}/${roundMeta.maxRounds}`;
  }, [loading, roundMeta]);

  const technicalLines = useMemo(() => {
    const lines = [];
    events.slice(-30).forEach((event) => {
      const payload = event.payload || {};
      if (event.type === "round_started") {
        const maxLabel = payload.max_rounds ? `/${payload.max_rounds}` : "";
        lines.push(`Round ${payload.round || "?"}${maxLabel} started`);
      } else if (event.type === "step_started") {
        lines.push(`${toTitle(payload.step || "Step")} started`);
      } else if (event.type === "step_completed") {
        lines.push(`${toTitle(payload.step || "Step")} completed`);
      } else if (event.type === "tool_started") {
        lines.push(`Tool started: ${payload.tool || "tool"}`);
      } else if (event.type === "tool_completed") {
        lines.push(`Tool completed: ${payload.tool || "tool"}`);
      } else if (event.type === "auto_rerun") {
        lines.push(`Re-run triggered: ${payload.reason || "Optimization needed"}`);
      } else if (event.type === "error") {
        lines.push(`Error: ${payload.message || "Unexpected error"}`);
      }
    });
    return lines.slice(-12);
  }, [events]);

  function onSocketEvent(event) {
    const type = event.type;
    if (type === "snapshot") {
      const snapshotEvents = Array.isArray(event.events) ? event.events : [];
      setEvents(snapshotEvents.map((e) => ({ type: e.type, payload: e })));
      if (event.report) {
        setReport(event.report);
      }
      // Avoid start-click race: keep loading true if a run has just been initiated locally.
      setLoading((prev) => prev || Boolean(event.running));
      if (snapshotEvents.length > 0) {
        setCurrentStatus(eventToStatus(snapshotEvents[snapshotEvents.length - 1]));
      } else {
        setCurrentStatus(event.running ? "Planning in progress..." : "Ready.");
      }
      return;
    }

    setEvents((prev) => [...prev, { type, payload: event }].slice(-300));
    setCurrentStatus(eventToStatus(event));
    if (type === "run_started" || type === "round_started" || type === "step_started" || type === "auto_rerun") {
      setLoading(true);
    }
    if (type === "report_ready" || type === "completed" || type === "aborted") {
      setReport(event.final_report || event.report || null);
    }
    if (type === "completed" || type === "aborted") {
      setLoading(false);
      if (type === "completed") {
        const passes = Number(event.round || 1);
        const passLabel = passes > 1 ? "passes" : "pass";
        setMessages((prev) => [
          ...prev,
          { role: "assistant", text: `Finalized after ${passes} ${passLabel}${passes > 1 ? " for better budget fit." : "."}` },
        ]);
      }
      if (pendingRefineRef.current) {
        setMessages((prev) => [...prev, { role: "assistant", text: "Plan updated. See refreshed report below." }]);
        pendingRefineRef.current = false;
      }
    }
    if (type === "error") {
      setLoading(false);
      setError(event.message || "Unexpected websocket error");
      pendingRefineRef.current = false;
    }
  }

  function clearStaleSession(message = "Previous session expired. Start a new plan.") {
    suppressReconnectRef.current = true;
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (wsRef.current) {
      try {
        wsRef.current.close();
      } catch {
        // no-op
      }
    }
    wsRef.current = null;
    wsConnectPromiseRef.current = null;
    pendingRefineRef.current = false;

    sessionStorage.removeItem(HOME_STATE_KEY);
    setSessionId("");
    setEvents([]);
    setMessages([]);
    setReport(null);
    setLoading(false);
    setChatInput("");
    setSocketReady(false);
    setCurrentStatus("Ready to start planning.");
    setShowDetails(false);
    setError(message);
    setTimeout(() => {
      suppressReconnectRef.current = false;
    }, 80);
  }

  async function syncFromSnapshot(id) {
    const res = await fetchSessionSnapshot(id);
    if (res.status === 404) {
      clearStaleSession("Previous session no longer exists on backend. Start a new plan.");
      return false;
    }
    if (!res.ok) return false;
    const snap = await res.json();
    const snapshotEvents = Array.isArray(snap.events) ? snap.events : [];
    setEvents(snapshotEvents.map((e) => ({ type: e.type, payload: e })));
    if (snap.report) {
      setReport(snap.report);
    }
    setLoading(Boolean(snap.running));
    if (snapshotEvents.length > 0) {
      setCurrentStatus(eventToStatus(snapshotEvents[snapshotEvents.length - 1]));
    } else {
      setCurrentStatus(snap.running ? "Planning in progress..." : "Ready.");
    }
    return true;
  }

  function connectSessionSocket(id, requestSync = false) {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      if (requestSync) {
        sendPlannerSocketAction(wsRef.current, "sync");
      }
      return Promise.resolve(wsRef.current);
    }
    if (wsConnectPromiseRef.current) {
      return wsConnectPromiseRef.current;
    }

    if (wsRef.current && wsRef.current.readyState === WebSocket.CONNECTING) {
      return Promise.reject(new Error("WebSocket is connecting."));
    }

    wsConnectPromiseRef.current = new Promise((resolve, reject) => {
      const ws = createPlannerSocket(id, {
        onOpen: () => {
          setSocketReady(true);
          wsConnectPromiseRef.current = null;
          if (requestSync) {
            sendPlannerSocketAction(ws, "sync");
          }
          resolve(ws);
        },
        onEvent: (event) => {
          if (event?.type === "error" && String(event?.message || "").includes("Unknown session_id")) {
            clearStaleSession("Previous session no longer exists on backend. Start a new plan.");
            return;
          }
          onSocketEvent(event);
        },
        onError: () => {
          setSocketReady(false);
          wsConnectPromiseRef.current = null;
          reject(new Error("WebSocket connection failed."));
        },
        onClose: () => {
          if (wsRef.current === ws) {
            wsRef.current = null;
          }
          setSocketReady(false);
          wsConnectPromiseRef.current = null;
          if (!suppressReconnectRef.current && id && !reconnectTimerRef.current) {
            reconnectTimerRef.current = setTimeout(() => {
              reconnectTimerRef.current = null;
              connectSessionSocket(id, true).catch(() => {
                // keep silent; next user action will surface errors
              });
            }, 1200);
          }
        },
      });
      wsRef.current = ws;
    });
    return wsConnectPromiseRef.current;
  }

  function runViaSocket(action, message = "") {
    sendPlannerSocketAction(wsRef.current, action, message);
  }

  async function createSessionAndRun() {
    setError("");
    setLoading(true);
    setEvents([]);
    setReport(null);
    setCurrentStatus("Starting your trip planning run...");
    if (wsRef.current) {
      suppressReconnectRef.current = true;
      try {
        wsRef.current.close();
      } catch {
        // no-op
      }
      wsRef.current = null;
      wsConnectPromiseRef.current = null;
      setSocketReady(false);
      setTimeout(() => {
        suppressReconnectRef.current = false;
      }, 50);
    }
    try {
      const data = await createPlannerSession(form);
      setSessionId(data.session_id);
      setMessages([{ role: "user", text: "Start planning my trip." }]);
      await connectSessionSocket(data.session_id);
      runViaSocket("start", "");
      setLoading(true);
    } catch (e) {
      setError(e.message || "Unexpected error");
      setLoading(false);
    }
  }

  async function onRefine() {
    if (!chatInput.trim() || !sessionId || !socketReady) return;
    const text = chatInput.trim();
    setChatInput("");
    setMessages((prev) => [...prev, { role: "user", text }]);
    setLoading(true);
    setError("");
    setCurrentStatus("Applying your requested changes...");
    try {
      pendingRefineRef.current = true;
      runViaSocket("refine", text);
      setLoading(true);
    } catch (e) {
      setError(e.message || "Refinement failed");
      setLoading(false);
      pendingRefineRef.current = false;
    }
  }

  async function stopAndReset() {
    if (sessionId) {
      try {
        await stopPlannerSession(sessionId);
      } catch {
        // best-effort stop request
      }
    }

    suppressReconnectRef.current = true;
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (wsRef.current) {
      try {
        wsRef.current.close();
      } catch {
        // no-op
      }
    }
    wsRef.current = null;
    wsConnectPromiseRef.current = null;
    pendingRefineRef.current = false;

    sessionStorage.removeItem(HOME_STATE_KEY);
    setSessionId("");
    setEvents([]);
    setMessages([]);
    setReport(null);
    setLoading(false);
    setError("");
    setChatInput("");
    setSocketReady(false);
    setCurrentStatus("Ready to start planning.");
    setShowDetails(false);
    setTimeout(() => {
      suppressReconnectRef.current = false;
    }, 80);
  }

  return {
    form,
    setForm,
    loading,
    error,
    hasStarted,
    stepStatus,
    messages,
    currentStatus,
    passBadgeText,
    technicalLines,
    showDetails,
    setShowDetails,
    chatInput,
    setChatInput,
    sessionId,
    socketReady,
    report,
    createSessionAndRun,
    onRefine,
    stopAndReset,
  };
}
