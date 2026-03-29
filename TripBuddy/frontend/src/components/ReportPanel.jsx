import { useState } from "react";
import { toTitle } from "../utils/planner";

const DETAIL_SECTIONS = new Set([
  "governance",
  "accountability",
  "decision_trace",
  "explainability",
  "assurance",
  "trust",
  "fairness",
  "ethical_checks",
  "autonomy",
  "imda_alignment",
]);
const FRIENDLY_LABELS = {
  required_fields_complete: "Required plan fields complete",
  budget_consistency: "Budget calculation consistent",
  budget_within_limit: "Budget within user limit",
  flight_tool_evidence: "Flight evidence available",
  multi_signal_destination_validation: "Multiple sources validated the destination",
  fallback_pressure: "Fallback pressure acceptable",
  sponsored_bias_control: "No sponsored ranking bias",
  dietary_constraint_respected: "Dietary constraints respected",
  option_diversity: "Option diversity checked",
  stable_tie_breaking: "Stable ranking fallback",
  dietary_needs_preserved: "Dietary needs preserved",
  budget_transparency: "Budget transparency provided",
  coercive_language_absent: "No coercive language detected",
  destination_risk_keywords: "No high-risk destination keyword matched",
};
const TOOL_LABELS = {
  FlightAPI: "Flight search tool",
  WeatherAPI: "Weather tool",
  TouristAttractionAPI: "Attraction search tool",
  food_catalog: "Food planning tool",
  food_search_live: "Live dining tool",
  AccomsAPI: "Accommodation search tool",
  places_search: "Place search tool",
  route_estimate: "Route estimate tool",
  place_signals: "Place signals tool",
};

function statusClass(value) {
  const normalized = String(value || "").toLowerCase();
  if (["approved", "clear", "stronger", "success"].includes(normalized)) return "good";
  if (["partial", "review", "needs_review", "failed"].includes(normalized)) return "warn";
  return "";
}

function statusText(value) {
  if (typeof value === "boolean") return value ? "Pass" : "Review";
  const normalized = String(value || "");
  if (!normalized) return "";
  if (normalized === "needs_review") return "Needs Review";
  return toTitle(normalized.replaceAll("_", " "));
}

function renderText(value) {
  const text = String(value || "").replace(/\r\n/g, "\n").trim();
  if (!text) return <span></span>;

  const lines = text.split("\n").map((line) => line.trimEnd());
  const groupedItems = [];
  let current = null;
  for (const raw of lines) {
    const line = raw.trim();
    if (!line) continue;
    if (line.startsWith("- ")) {
      if (current) groupedItems.push(current);
      current = line.slice(2).trim();
      continue;
    }
    if (current) {
      current += `\n${line}`;
    }
  }
  if (current) groupedItems.push(current);

  if (groupedItems.length >= 2) {
    return (
      <ul className="report-text-list">
        {groupedItems.map((item, i) => (
          <li key={i}>
            <span className="report-bullet-text">{item}</span>
          </li>
        ))}
      </ul>
    );
  }

  if (text.startsWith("- ") && text.includes(" - ")) {
    const inlineItems = text
      .replace(/^\-\s*/, "")
      .split(/\s-\s+/)
      .map((item) => item.trim())
      .filter(Boolean);
    if (inlineItems.length >= 2) {
      return (
        <ul className="report-text-list">
          {inlineItems.map((item, i) => (
            <li key={i}>{item}</li>
          ))}
        </ul>
      );
    }
  }

  const paragraphs = text
    .split(/\n{2,}/)
    .map((p) => p.trim())
    .filter(Boolean);
  if (paragraphs.length >= 2) {
    return (
      <div className="report-text-block">
        {paragraphs.map((p, i) => (
          <p className="report-text" key={i}>
            {p}
          </p>
        ))}
      </div>
    );
  }

  return <p className="report-text">{text}</p>;
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
            <span className={statusClass(v)}>{toTitle(k.replaceAll("_", " "))}</span>
            <div>{reportValue(v)}</div>
          </div>
        ))}
      </div>
    );
  }
  if (typeof value === "boolean") {
    return <span className={`status-pill ${value ? "good" : "warn"}`}>{value ? "Pass" : "Review"}</span>;
  }
  if (typeof value === "string") {
    if (statusClass(value)) {
      return <span className={`status-pill ${statusClass(value)}`}>{statusText(value)}</span>;
    }
    return <div>{renderText(value)}</div>;
  }
  return <span>{String(value)}</span>;
}

function shortHash(value) {
  const text = String(value || "");
  if (text.length <= 18) return text;
  return `${text.slice(0, 8)}...${text.slice(-6)}`;
}

function summarizePolicySection(key, value) {
  if (!value || typeof value !== "object") return reportValue(value);

  if (key === "governance") {
    const toolsObserved = Array.isArray(value.tools_observed) ? value.tools_observed.map((tool) => TOOL_LABELS[tool] || tool) : [];
    return (
      <div className="policy-summary">
        <p className="report-text">This plan was produced under a governed workflow with versioned decision rules and restricted tool access.</p>
        <div className="summary-badges">
          <span className="summary-chip">Policy {value.policy_version || "N/A"}</span>
          <span className="summary-chip">Schema {value.report_schema_version || "N/A"}</span>
          <span className="summary-chip">{toolsObserved.length} governed tools</span>
        </div>
      </div>
    );
  }

  if (key === "accountability") {
    return (
      <div className="policy-summary">
        <p className="report-text">A traceable audit record exists for this run, including a stable audit ID, execution run ID, tool calls, and trace hash.</p>
        <div className="summary-badges">
          <span className="summary-chip">Audit tracked</span>
          <span className="summary-chip">{value.tool_call_count || 0} tool calls</span>
          <span className="summary-chip">Trace {shortHash(value.trace_hash)}</span>
        </div>
      </div>
    );
  }

  if (key === "decision_trace") {
    const entries = Array.isArray(value) ? value : [];
    return (
      <ul className="summary-list timeline-list">
        {entries.map((entry, index) => (
          <li key={index}>
            <strong>{entry.stage || "Step"}:</strong> {entry.summary || "No summary"}{" "}
            {entry.tools_used ? `(${entry.tools_used} tools)` : ""}
          </li>
        ))}
      </ul>
    );
  }

  if (key === "explainability") {
    const breakdown = Array.isArray(value.score_breakdown) ? value.score_breakdown.slice(0, 3) : [];
    return (
      <div className="policy-summary">
        <p className="report-text">{value.summary || "No explainability summary available."}</p>
        {breakdown.length > 0 && (
          <ul className="summary-list">
            {breakdown.map((item, index) => (
              <li key={index}>
                {toTitle(String(item.criterion || "").replaceAll("_", " "))}: {item.score}
              </li>
            ))}
          </ul>
        )}
      </div>
    );
  }

  if (key === "assurance") {
    const checks = Array.isArray(value.validation_checks) ? value.validation_checks : [];
    const failed = checks.filter((item) => item && item.passed === false).length;
    return (
      <div className="policy-summary">
        <div className="summary-badges">
          <span className="summary-chip">Confidence {value.confidence_score ?? "N/A"}</span>
          <span className={`status-pill ${statusClass(value.approval_gate)}`}>{statusText(value.approval_gate || "N/A")}</span>
        </div>
        <p className="report-text">
          {failed ? `${failed} assurance checks need review before treating this plan as high confidence.` : "All assurance checks passed for this run."}
        </p>
      </div>
    );
  }

  if (key === "trust") {
    return (
      <div className="policy-summary">
        <div className="summary-badges">
          <span className="summary-chip">Trust {value.score ?? "N/A"}</span>
        </div>
        <p className="report-text">{value.user_visible_reason || "No trust explanation available."}</p>
      </div>
    );
  }

  if (key === "fairness") {
    const checks = Array.isArray(value.checks) ? value.checks : [];
    const failed = checks.filter((item) => item && item.passed === false).length;
    return (
      <div className="policy-summary">
        <div className="summary-badges">
          <span className={`status-pill ${statusClass(value.status)}`}>{statusText(value.status || "N/A")}</span>
          <span className="summary-chip">{Array.isArray(value.mitigations) ? value.mitigations.length : 0} mitigations</span>
        </div>
        <p className="report-text">
          {failed ? `${failed} fairness checks need attention.` : "Fairness checks passed with bias-mitigation safeguards applied."}
        </p>
      </div>
    );
  }

  if (key === "ethical_checks") {
    const checks = Array.isArray(value.checks) ? value.checks : [];
    const failed = checks.filter((item) => item && item.passed === false).length;
    return (
      <div className="policy-summary">
        <div className="summary-badges">
          <span className={`status-pill ${statusClass(value.status)}`}>{statusText(value.status || "N/A")}</span>
          <span className="summary-chip">{Array.isArray(value.rule_engine?.coercive_language_patterns) ? value.rule_engine.coercive_language_patterns.length : 0} rule patterns</span>
        </div>
        <p className="report-text">
          {failed ? `${failed} ethical checks need review.` : "No ethical warning rules were triggered for this plan."}
        </p>
      </div>
    );
  }

  if (key === "autonomy") {
    const triggers = Array.isArray(value.triggers) ? value.triggers : [];
    return (
      <div className="policy-summary">
        <div className="summary-badges">
          <span className="summary-chip">Auto-rerun {value.auto_rerun_enabled ? "On" : "Off"}</span>
          <span className="summary-chip">Next: {statusText(value.next_action || "N/A")}</span>
        </div>
        <p className="report-text">
          {triggers.length ? `This run flagged: ${triggers.join(", ")}.` : "No additional replanning triggers were active for this run."}
        </p>
      </div>
    );
  }

  if (key === "imda_alignment") {
    const values = Object.values(value);
    const stronger = values.filter((item) => String(item) === "stronger").length;
    const partial = values.filter((item) => String(item) === "partial").length;
    const review = values.filter((item) => String(item) === "review").length;
    return (
      <div className="policy-summary">
        <p className="report-text">This is the high-level policy maturity snapshot for the current plan.</p>
        <div className="summary-badges">
          <span className="summary-chip">{stronger} stronger</span>
          <span className="summary-chip">{partial} partial</span>
          <span className="summary-chip">{review} review</span>
        </div>
      </div>
    );
  }

  return reportValue(value);
}

export function ReportPanel({ report }) {
  const [showPolicyDetails, setShowPolicyDetails] = useState(false);
  const blocks =
    !report || typeof report !== "object"
      ? []
      : Object.entries(report).filter(([key]) => key !== "decision_trace_full");
  const fullTrace =
    report && typeof report === "object" && Array.isArray(report.decision_trace_full)
      ? report.decision_trace_full
      : [];

  function prettyDetailValue(key, value) {
    if (Array.isArray(value)) {
      return (
        <ul>
          {value.map((entry, index) => (
            <li key={index}>{prettyDetailValue(key, entry)}</li>
          ))}
        </ul>
      );
    }
    if (value && typeof value === "object") {
      return (
        <div className="kv-grid">
          {Object.entries(value).map(([childKey, childValue]) => (
            <div className="kv-item" key={childKey}>
              <span className={statusClass(childValue)}>
                {FRIENDLY_LABELS[childKey] || toTitle(childKey.replaceAll("_", " "))}
              </span>
              <div>{prettyDetailValue(childKey, childValue)}</div>
            </div>
          ))}
        </div>
      );
    }
    return reportValue(value);
  }

  return (
    <section className="panel report-panel">
      <h2>Travel Plan Report</h2>
      {!report && <p>Your final plan will appear here after planning completes.</p>}
      {blocks.map(([k, v]) => (
        <article key={k} className="report-block">
          <h3>{toTitle(k.replaceAll("_", " "))}</h3>
          {DETAIL_SECTIONS.has(k) ? summarizePolicySection(k, v) : reportValue(v)}
        </article>
      ))}
      {blocks.some(([key]) => DETAIL_SECTIONS.has(key)) && (
        <section className="panel audit-panel">
          <div className="audit-panel-head">
            <h2>Plan Governance Details</h2>
            <button
              type="button"
              className="trace-toggle-btn"
              onClick={() => setShowPolicyDetails((prev) => !prev)}
            >
              {showPolicyDetails ? "Hide Detailed Evidence" : "Show Detailed Evidence"}
            </button>
          </div>
          <p className="report-text">
            This section is meant for advanced review, audit, or debugging. Most travelers should only need the summaries above.
          </p>
          {showPolicyDetails && (
            <div className="audit-detail-stack">
              {blocks
                .filter(([key]) => DETAIL_SECTIONS.has(key))
                .map(([key, value]) => (
                  <article key={key} className="report-block audit-detail-block">
                    <h3>{toTitle(key.replaceAll("_", " "))}</h3>
                    {key === "decision_trace" && fullTrace.length > 0
                      ? prettyDetailValue(key, fullTrace)
                      : prettyDetailValue(key, value)}
                  </article>
                ))}
            </div>
          )}
        </section>
      )}
    </section>
  );
}
