import { Link } from "react-router-dom";

export function HelpPage() {
  return (
    <div className="page">
      <header className="topbar">
        <h1>TripBuddy Tutorial</h1>
        <Link to="/">Back to Planner</Link>
      </header>
      <section className="panel help">
        <h2>Plan a Trip with few simple steps</h2>
        <ol>
          <li>Fill in travel days, budget, country, optional city, start date, and dietary restrictions.</li>
          <li>Click Start Planning to trigger all agents.</li>
          <li>Watch live steps update as each specialist completes work.</li>
          <li>Use chat to request edits like cheaper hotels, different activities, or food changes.</li>
          <li>Review the final report.</li>
          <li>Click Reset to clear results and plan another trip.</li>
        </ol>
      </section>
    </div>
  );
}
