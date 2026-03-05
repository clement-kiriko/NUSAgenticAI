import { toTitle } from "../utils/planner";

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

export function ReportPanel({ report }) {
  const blocks = !report || typeof report !== "object" ? [] : Object.entries(report);
  return (
    <section className="panel report-panel">
      <h2>Travel Plan Report</h2>
      {!report && <p>Your final plan will appear here after planning completes.</p>}
      {blocks.map(([k, v]) => (
        <article key={k} className="report-block">
          <h3>{toTitle(k.replaceAll("_", " "))}</h3>
          {reportValue(v)}
        </article>
      ))}
    </section>
  );
}
