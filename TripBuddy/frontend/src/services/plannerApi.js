const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export async function createPlannerSession(form) {
  const res = await fetch(`${API_BASE}/api/session`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(form),
  });
  if (!res.ok) {
    throw new Error("Could not create session");
  }
  return res.json();
}

export async function fetchSessionSnapshot(sessionId) {
  return fetch(`${API_BASE}/api/session/${sessionId}/snapshot`);
}

export async function stopPlannerSession(sessionId) {
  return fetch(`${API_BASE}/api/session/${sessionId}/stop`, { method: "POST" });
}
