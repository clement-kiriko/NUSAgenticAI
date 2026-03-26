import { useState } from "react";
import { DIETARY_OPTIONS, getTodayLocalIso } from "../utils/travelForm";

const ALL_FIELDS = ["days", "budget_sgd", "country", "start_date", "dietary_restrictions"];

export function TravelForm({ form, updateFormField, validationErrors, loading, error, onStart }) {
  const [touched, setTouched] = useState({});
  const [submitted, setSubmitted] = useState(false);

  function markTouched(field) {
    setTouched((prev) => ({ ...prev, [field]: true }));
  }

  function shouldShowError(field) {
    return Boolean(validationErrors[field]) && (submitted || touched[field]);
  }

  function handleStart() {
    setSubmitted(true);
    setTouched((prev) => {
      const next = { ...prev };
      ALL_FIELDS.forEach((field) => {
        next[field] = true;
      });
      return next;
    });
    onStart();
  }

  return (
    <section className="panel form-panel">
      <h2>Travel Query</h2>
      <label className={shouldShowError("days") ? "field-error" : ""}>
        Travel Days
        <input
          type="number"
          min="1"
          step="1"
          value={form.days}
          onChange={(e) => updateFormField("days", e.target.value)}
          onBlur={() => markTouched("days")}
          aria-invalid={shouldShowError("days")}
        />
        {shouldShowError("days") && <span className="error field-error-text">{validationErrors.days}</span>}
      </label>
      <label className={shouldShowError("budget_sgd") ? "field-error" : ""}>
        Total Budget (SGD)
        <input
          type="number"
          min="1"
          step="0.01"
          value={form.budget_sgd}
          onChange={(e) => updateFormField("budget_sgd", e.target.value)}
          onBlur={() => markTouched("budget_sgd")}
          aria-invalid={shouldShowError("budget_sgd")}
        />
        {shouldShowError("budget_sgd") && (
          <span className="error field-error-text">{validationErrors.budget_sgd}</span>
        )}
      </label>
      <label className={shouldShowError("country") ? "field-error" : ""}>
        Country to Visit
        <input
          value={form.country}
          onChange={(e) => updateFormField("country", e.target.value)}
          onBlur={() => markTouched("country")}
          aria-invalid={shouldShowError("country")}
        />
        {shouldShowError("country") && <span className="error field-error-text">{validationErrors.country}</span>}
      </label>
      <label className={shouldShowError("start_date") ? "field-error" : ""}>
        Travel Start Date
        <input
          type="date"
          value={form.start_date}
          min={getTodayLocalIso()}
          onChange={(e) => updateFormField("start_date", e.target.value)}
          onBlur={() => markTouched("start_date")}
          aria-invalid={shouldShowError("start_date")}
        />
        {shouldShowError("start_date") && (
          <span className="error field-error-text">{validationErrors.start_date}</span>
        )}
      </label>
      <label>
        Dietary Restrictions
        <select
          value={form.dietary_restrictions}
          onChange={(e) => updateFormField("dietary_restrictions", e.target.value)}
          onBlur={() => markTouched("dietary_restrictions")}
        >
          {DIETARY_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      <div className="form-actions">
        {error && <p className="error">{error}</p>}
        <button disabled={loading} onClick={handleStart}>
          {loading ? "Planning..." : "Start Planning"}
        </button>
      </div>
    </section>
  );
}
