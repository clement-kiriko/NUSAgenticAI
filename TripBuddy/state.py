from typing import TypedDict, Optional, List, Any

# Define the structure of our shared state for LangGraph ≥0.2
class TripState(TypedDict, total=False):
    user_input: str
    conversation: List[Any]
    trip_options: List[Any]
    next: str
    destination_done: bool
    budget_done: bool
    schedule_done: bool
    final_summary: Optional[dict]

