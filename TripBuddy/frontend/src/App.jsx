import { useEffect, useMemo, useRef, useState } from "react";
import { Link, Navigate, Route, Routes } from "react-router-dom";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";
const WS_BASE = (import.meta.env.VITE_WS_BASE || API_BASE).replace(/^http/, "ws");
const HOME_STATE_KEY = "tripbuddy_home_state_v1";
const STEP_ORDER = [
  "orchestrator",
  "flight",
  "locations",
  "food",
  "accomodations",
  "budget",
  "consolidation",
];

function toTitle(value) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function eventToStatus(event) {
  if (!event) return "Ready to start planning.";
  const type = event.type;
  if (event.message) return event.message;
  if (type === "tool_started") return "Checking live data sources...";
  if (type === "tool_completed") return "Live data received.";
  if (type === "step_started") return `Working on ${toTitle(event.step)}...`;
  if (type === "step_completed") return `${toTitle(event.step)} completed.`;
  if (type === "report_ready") return "Finalizing your travel plan report...";
  if (type === "completed") return "Planning completed.";
  if (type === "aborted") return event.message || "Planning stopped.";
  if (type === "auto_rerun") return "Optimizing plan to better fit your budget...";
  if (type === "run_started") return "Planning started.";
  if (type === "run_finished") return "Run finished.";
  if (type === "error") return event.message || "An error occurred.";
  return "Planning in progress...";
}

function reportBlocks(report) {
  if (!report || typeof report !== "object") return [];
  return Object.entries(report);
}

function reportValue(value) {
  if (Array.isArray(value)) {
    return (
      <ul>
        {value.map((entry, i) => (
          <li key={i}>{reportValue(entry)}</li>
        ))}
      </ul>
    );
  }
  if (value && typeof value === "object") {
    return (
      <div className="kv-grid">
        {Object.entries(value).map(([k, v]) => (
          <div className="kv-item" key={k}>
            <span>{toTitle(k.replaceAll("_", " "))}</span>
            <div>{reportValue(v)}</div>
          </div>
        ))}
      </div>
    );
  }
  return <span>{String(value)}</span>;
}

function HomePage() {
  const savedState = (() => {
    try {
      const raw = sessionStorage.getItem(HOME_STATE_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  })();

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
      setLoading(Boolean(event.running));
      if (snapshotEvents.length > 0) {
        setCurrentStatus(eventToStatus(snapshotEvents[snapshotEvents.length - 1]));
      } else {
        setCurrentStatus(event.running ? "Planning in progress..." : "Ready.");
      }
      return;
    }

    setEvents((prev) => [...prev, { type, payload: event }].slice(-300));
    setCurrentStatus(eventToStatus(event));
    if (type === "report_ready" || type === "completed" || type === "aborted") {
      setReport(event.final_report || event.report || null);
    }
    if (type === "completed" || type === "aborted") {
      setLoading(false);
      if (type === "completed") {
        const passes = Number(event.round || 1);
        const passLabel = passes > 1 ? `passes` : "pass";
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
    const res = await fetch(`${API_BASE}/api/session/${id}/snapshot`);
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
        wsRef.current.send(JSON.stringify({ action: "sync" }));
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
      const ws = new WebSocket(`${WS_BASE}/ws/session/${id}`);
      wsRef.current = ws;

      ws.onopen = () => {
        setSocketReady(true);
        wsConnectPromiseRef.current = null;
        if (requestSync) {
          ws.send(JSON.stringify({ action: "sync" }));
        }
        resolve(ws);
      };
      ws.onmessage = (msg) => {
        try {
          const event = JSON.parse(msg.data);
          if (event?.type === "error" && String(event?.message || "").includes("Unknown session_id")) {
            clearStaleSession("Previous session no longer exists on backend. Start a new plan.");
            return;
          }
          onSocketEvent(event);
        } catch {
          // ignore non-json frames
        }
      };
      ws.onerror = () => {
        setSocketReady(false);
        wsConnectPromiseRef.current = null;
        reject(new Error("WebSocket connection failed."));
      };
      ws.onclose = () => {
        if (wsRef.current === ws) {
          wsRef.current = null;
        }
        setSocketReady(false);
        wsConnectPromiseRef.current = null;
        // Auto-reconnect to resume status streaming for active session.
        if (!suppressReconnectRef.current && id && !reconnectTimerRef.current) {
          reconnectTimerRef.current = setTimeout(() => {
            reconnectTimerRef.current = null;
            connectSessionSocket(id, true).catch(() => {
              // keep silent; next user action will surface errors
            });
          }, 1200);
        }
      };
    });
    return wsConnectPromiseRef.current;
  }

  function runViaSocket(action, message = "") {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      throw new Error("WebSocket is not connected.");
    }
    wsRef.current.send(JSON.stringify({ action, message }));
  }

  async function createSessionAndRun() {
    setError("");
    setLoading(true);
    setEvents([]);
    setReport(null);
    setCurrentStatus("Starting your trip planning run...");
    // Starting a new session should fully replace old socket/session state.
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
      const res = await fetch(`${API_BASE}/api/session`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      if (!res.ok) throw new Error("Could not create session");
      const data = await res.json();
      setSessionId(data.session_id);
      setMessages([{ role: "user", text: "Start planning my trip." }]);
      await connectSessionSocket(data.session_id);
      runViaSocket("start", "");
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
    } catch (e) {
      setError(e.message || "Refinement failed");
      setLoading(false);
      pendingRefineRef.current = false;
    }
  }

  async function stopAndReset() {
    if (sessionId) {
      try {
        await fetch(`${API_BASE}/api/session/${sessionId}/stop`, { method: "POST" });
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

  return (
    <div className="page">
      <header className="topbar">
        <h1>TripBuddy</h1>
        <Link to="/help">How It Works</Link>
      </header>

      <main className="layout">
        <section className="panel form-panel">
          <h2>Travel Query</h2>
          <label>
            Travel Days
            <input
              type="number"
              min="1"
              value={form.days}
              onChange={(e) => setForm((p) => ({ ...p, days: Number(e.target.value) }))}
            />
          </label>
          <label>
            Total Budget (SGD)
            <input
              type="number"
              min="1"
              value={form.budget_sgd}
              onChange={(e) => setForm((p) => ({ ...p, budget_sgd: Number(e.target.value) }))}
            />
          </label>
          <label>
            Country to Visit
            <input value={form.country} onChange={(e) => setForm((p) => ({ ...p, country: e.target.value }))} />
          </label>
          <label>
            Travel Start Date
            <input
              type="date"
              value={form.start_date}
              onChange={(e) => setForm((p) => ({ ...p, start_date: e.target.value }))}
            />
          </label>
          <label>
            Dietary Restrictions
            <input
              value={form.dietary_restrictions}
              onChange={(e) => setForm((p) => ({ ...p, dietary_restrictions: e.target.value }))}
            />
          </label>
          <div className="form-actions">
            {error && <p className="error">{error}</p>}
            <button disabled={loading || !form.country || !form.start_date} onClick={createSessionAndRun}>
              {loading ? "Planning..." : "Start Planning"}
            </button>
          </div>
        </section>

        {!hasStarted && (
          <section className="panel chat-panel">
            <h2>Planner Chat</h2>
            <p>Chat and live status will appear after you click Start Planning.</p>
          </section>
        )}

        {hasStarted && (
          <section className="panel chat-panel">
            <h2>Planner Chat</h2>
            <div className="steps">
              {STEP_ORDER.map((step) => (
                <div className={`step ${stepStatus[step]}`} key={step}>
                  <span>{toTitle(step)}</span>
                  <small>{stepStatus[step]}</small>
                </div>
              ))}
            </div>
            <div className="messages">
              {messages.map((msg, i) => (
                <article className={`msg ${msg.role}`} key={i}>
                  {msg.text}
                </article>
              ))}
              <article className="msg assistant status-msg">{currentStatus}</article>
            </div>
            {passBadgeText && <p className="pass-badge">{passBadgeText}</p>}
            {technicalLines.length > 0 && (
              <details className="details-panel" open={showDetails} onToggle={(e) => setShowDetails(e.currentTarget.open)}>
                <summary>Details</summary>
                <div className="details-list">
                  {technicalLines.map((line, i) => (
                    <p key={`${line}-${i}`}>{line}</p>
                  ))}
                </div>
              </details>
            )}
            <div className="chat-input">
              <input
                placeholder="Let TripBuddy know what to adjust..."
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") onRefine();
                }}
              />
              <button disabled={loading || !sessionId || !socketReady} onClick={onRefine}>
                Send
              </button>
            </div>
            <div className="chat-footer">
              <button className="danger-btn" disabled={!hasStarted && !loading} onClick={stopAndReset}>
                Reset
              </button>
            </div>
          </section>
        )}
      </main>

      <section className="panel report-panel">
        <h2>Travel Plan Report</h2>
        {!report && <p>Your final plan will appear here after planning completes.</p>}
        {report &&
          reportBlocks(report).map(([k, v]) => (
            <article key={k} className="report-block">
              <h3>{toTitle(k.replaceAll("_", " "))}</h3>
              {reportValue(v)}
            </article>
          ))}
      </section>
    </div>
  );
}

function HelpPage() {
  return (
    <div className="page">
      <header className="topbar">
        <h1>TripBuddy Tutorial</h1>
        <Link to="/">Back to Planner</Link>
      </header>
      <section className="panel help">
        <h2>Plan a Trip with in just 6 steps</h2>
        <ol>
          <li>Fill in travel days, budget, country, start date, and dietary restrictions.</li>
          <li>Click Start Planning to trigger all agents.</li>
          <li>Watch live steps update as each specialist completes work.</li>
          <li>Use chat to request edits like cheaper hotels, different activities, or food changes.</li>
          <li>Review the final report.</li>
        </ol>
      </section>
    </div>
  );
}

export function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/help" element={<HelpPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
