from typing import Any, Dict, List, Optional, TypedDict


class TripState(TypedDict, total=False):
    user_requirements: Dict[str, Any]
    feedback: str
    report: Dict[str, Any]
    final_report: Optional[Dict[str, Any]]
    satisfied: bool
    auto_rerun: bool
    max_rounds: int
    optimization_hints: Dict[str, Any]
    conversation: List[Any]
    round_number: int
    tool_calls: List[Dict[str, Any]]
    flight_plan: Dict[str, Any]
    locations_plan: Dict[str, Any]
    food_plan: Dict[str, Any]
    accomodations_plan: Dict[str, Any]
    budget_plan: Dict[str, Any]
    governance_metadata: Dict[str, Any]
    policy_evaluation: Dict[str, Any]
    decision_trace: List[Dict[str, Any]]
    current_run_id: str
