from dotenv import load_dotenv
from langgraph.graph import END, START, StateGraph

from agents import (
    accomodations_agent,
    budget_agent,
    consolidation_agent,
    flight_agent,
    food_agent,
    locations_agent,
    orchestrator_agent,
)
from logging_setup import configure_logging
from monitoring import timed_agent_call
from nodes import feedback_node, feedback_router, intake_node
from state import TripState

load_dotenv(override=True)
configure_logging()


def build_graph():
    graph = StateGraph(TripState)
    graph.add_node("intake", intake_node)
    graph.add_node("orchestrator", orchestrator_agent)
    graph.add_node("flight", flight_agent)
    graph.add_node("locations", locations_agent)
    graph.add_node("food", food_agent)
    graph.add_node("accomodations", accomodations_agent)
    graph.add_node("budget", budget_agent)
    graph.add_node("consolidation", consolidation_agent)
    graph.add_node("feedback", feedback_node)

    graph.add_edge(START, "intake")
    graph.add_edge("intake", "orchestrator")
    graph.add_edge("orchestrator", "flight")
    graph.add_edge("flight", "locations")
    graph.add_edge("locations", "food")
    graph.add_edge("food", "accomodations")
    graph.add_edge("accomodations", "budget")
    graph.add_edge("budget", "consolidation")
    graph.add_edge("consolidation", "feedback")
    graph.add_conditional_edges(
        "feedback",
        feedback_router,
        {
            "end": END,
            "rerun": "orchestrator",
        },
    )
    return graph.compile()


def main():
    graph = build_graph()
    print(graph.get_graph().draw_ascii())
    print("Set DEBUG=true for verbose LLM/tool trace logs.")
    result = timed_agent_call("cli_run", graph.invoke, {})
    print("\nFinal Approved Report")
    print(result.get("final_report", result.get("report")))

if __name__ == "__main__":
    main()
