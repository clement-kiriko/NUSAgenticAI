import { toTitle } from "../utils/planner";

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
            <span>{toTitle(k.replaceAll("_", " "))}</span>
            <div>{reportValue(v)}</div>
          </div>
        ))}
      </div>
    );
  }
  if (typeof value === "string") {
    return renderText(value);
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
