import { STEP_ORDER, toTitle } from "../utils/planner";

export function ProgressSteps({ stepStatus }) {
  return (
    <div className="steps">
      {STEP_ORDER.map((step) => (
        <div className={`step ${stepStatus[step]}`} key={step}>
          <span>{toTitle(step)}</span>
          <small>{stepStatus[step]}</small>
        </div>
      ))}
    </div>
  );
}
