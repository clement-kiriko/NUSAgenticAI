export function TravelForm({ form, setForm, loading, error, onStart }) {
  return (
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
        <button disabled={loading || !form.country || !form.start_date} onClick={onStart}>
          {loading ? "Planning..." : "Start Planning"}
        </button>
      </div>
    </section>
  );
}
