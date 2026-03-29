export const STEP_ORDER = [
  "orchestrator",
  "flight",
  "locations",
  "food",
  "accomodations",
  "budget",
  "consolidation",
];

export function toTitle(value) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function rerunStatusMessage(event) {
  const triggers = Array.isArray(event.trigger_types) ? event.trigger_types : [];
  if (triggers.includes("budget_overrun")) return "Optimizing plan to fit your budget...";
  if (triggers.includes("missing_fields")) return "Completing missing parts of your plan...";
  if (triggers.includes("low_assurance")) return "Improving plan confidence and evidence coverage...";
  if (triggers.includes("ethical_review")) return "Reworking the plan to address policy checks...";
  return event.reason || "Optimizing your plan...";
}

export function eventToStatus(event) {
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
  if (type === "auto_rerun") return rerunStatusMessage(event);
  if (type === "run_started") return "Planning started.";
  if (type === "run_finished") return "Run finished.";
  if (type === "error") return event.message || "An error occurred.";
  return "Planning in progress...";
}
