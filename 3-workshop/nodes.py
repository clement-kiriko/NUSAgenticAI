from agents import coordinator
from agents import destination
from agents import budget
from agents import scheduler
from agents import summarizer
from tools import trip_data_tool

def human_node(state: dict) -> dict:
    """Entry node: collect the user prompt and init conversation."""
    print("\n👤 Human input:")
    state["user_input"] = input("Enter your trip request: ").strip()
    state["conversation"] = [("human", state["user_input"])]
    return state


def coordinator_router(state: dict) -> dict:
    """
    Manual router for older langgraph (no `condition=` support).
    It looks at state['next'] and calls the correct expert/tool.
    Every expert/tool appends to conversation and returns the same state dict.
    """
    nxt = state.get("next")

    # First-time tool fetch
    if "trip_options" not in state:
        return trip_data_tool(state)

    if nxt in ("destination", "repeat_destination"):
        return destination(state)

    if nxt in ("budget", "repeat_budget"):
        return budget(state)

    if nxt in ("scheduler", "repeat_scheduler"):
        return scheduler(state)

    if nxt == "summarizer":
        return summarizer(state)

    # If coordinator hasn't decided yet, just return state (coordinator will run again)
    return state