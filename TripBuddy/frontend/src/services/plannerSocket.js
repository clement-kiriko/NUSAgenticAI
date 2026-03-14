const API_BASE =
  import.meta.env.VITE_API_BASE ||
  (import.meta.env.DEV ? "http://localhost:8000" : window.location.origin);
const WS_BASE = (import.meta.env.VITE_WS_BASE || API_BASE).replace(/^http/, "ws");

export function createPlannerSocket(sessionId, handlers) {
  const ws = new WebSocket(`${WS_BASE}/ws/session/${sessionId}`);

  ws.onopen = () => handlers.onOpen?.(ws);
  ws.onmessage = (msg) => {
    try {
      const event = JSON.parse(msg.data);
      handlers.onEvent?.(event, ws);
    } catch {
      // ignore non-json frames
    }
  };
  ws.onerror = () => handlers.onError?.(ws);
  ws.onclose = () => handlers.onClose?.(ws);

  return ws;
}

export function sendPlannerSocketAction(ws, action, message = "") {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    throw new Error("WebSocket is not connected.");
  }
  ws.send(JSON.stringify({ action, message }));
}
