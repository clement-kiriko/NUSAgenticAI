import json
from datetime import datetime, timedelta


def _prompt_non_empty(prompt: str) -> str:
    while True:
        value = input(prompt).strip()
        if value:
            return value
        print("Please enter a non-empty value.")


def _prompt_positive_int(prompt: str) -> int:
    while True:
        value = input(prompt).strip()
        try:
            parsed = int(value)
            if parsed > 0:
                return parsed
        except ValueError:
            pass
        print("Please enter a valid positive whole number.")


def _prompt_positive_float(prompt: str) -> float:
    while True:
        value = input(prompt).strip()
        try:
            parsed = float(value)
            if parsed > 0:
                return parsed
        except ValueError:
            pass
        print("Please enter a valid positive number.")


def _prompt_date(prompt: str) -> str:
    while True:
        value = input(prompt).strip()
        try:
            datetime.strptime(value, "%Y-%m-%d")
            return value
        except ValueError:
            print("Please use YYYY-MM-DD format, for example 2026-12-01.")


def _compute_end_date(start_date: str, days: int) -> str:
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = start + timedelta(days=days - 1)
    return end.isoformat()


def intake_node(state: dict) -> dict:
    print("\nTrip Advisor Intake")
    days = _prompt_positive_int("How many travel days? ")
    budget_sgd = _prompt_positive_float("Total trip budget (SGD)? ")
    country = _prompt_non_empty("Country to visit? ")
    city = input("City to visit? (optional): ").strip()
    start_date = _prompt_date("Travel start date (YYYY-MM-DD)? ")
    end_date = _compute_end_date(start_date, days)
    dietary_restrictions = input("Dietary restrictions? (enter 'none' if not applicable): ").strip() or "none"

    requirements = {
        "days": days,
        "budget_sgd": budget_sgd,
        "country": country,
        "city": city,
        "location_preference": f"{city}, {country}" if city else country,
        "start_date": start_date,
        "end_date": end_date,
        "dietary_restrictions": dietary_restrictions,
    }
    state["user_requirements"] = requirements
    state["feedback"] = ""
    state["satisfied"] = False
    state["auto_rerun"] = False
    state["round_number"] = 0
    state["max_rounds"] = 3
    state["optimization_hints"] = {}
    state["tool_calls"] = []
    state["conversation"] = [("human_intake", requirements)]
    return state


def feedback_node(state: dict) -> dict:
    report = state.get("report", {})
    print("\n=== Consolidated Trip Report ===")
    print(json.dumps(report, indent=2))

    within_budget = bool(state.get("budget_plan", {}).get("within_budget", False))
    round_number = int(state.get("round_number", 1))
    max_rounds = int(state.get("max_rounds", 3))

    if not within_budget and round_number < max_rounds:
        state["auto_rerun"] = True
        state["satisfied"] = False
        state["feedback"] = (
            "Current plan exceeds budget. Revise using optimization_hints and swap to cheaper "
            "flight/food/attraction/accommodation options while preserving trip quality."
        )
        print(
            f"\nPlan exceeds budget. Auto-optimizing and starting round {round_number + 1} "
            f"(max {max_rounds} rounds)."
        )
        state.setdefault("conversation", []).append(("system_auto_feedback", state["feedback"]))
        return state

    state["auto_rerun"] = False
    if not within_budget:
        print(f"\nBudget still exceeds limit after {max_rounds} rounds. Please choose trade-offs manually.")

    while True:
        answer = input("\nAre you satisfied with this plan? (yes/no): ").strip().lower()
        if answer in {"y", "yes", "n", "no"}:
            break
        print("Please answer with yes or no.")
    state["satisfied"] = answer in {"y", "yes"}
    if state["satisfied"]:
        state["final_report"] = report
        state["feedback"] = ""
    else:
        state["feedback"] = _prompt_non_empty("What should the agents improve? ")
        if round_number >= max_rounds:
            print(f"Reached max rounds ({max_rounds}). Returning current best plan.")
            state["final_report"] = report
    state.setdefault("conversation", []).append(("human_feedback", state.get("feedback", "")))
    return state


def feedback_router(state: dict) -> str:
    if state.get("auto_rerun"):
        return "rerun"
    round_number = int(state.get("round_number", 1))
    max_rounds = int(state.get("max_rounds", 3))
    if round_number >= max_rounds:
        return "end"
    return "end" if state.get("satisfied") else "rerun"
