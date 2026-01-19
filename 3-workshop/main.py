from dotenv import load_dotenv
from langgraph.graph import StateGraph, START, END
from agents import coordinator
from agents import destination
from agents import budget
from agents import scheduler
from agents import summarizer
from tools import trip_data_tool
from nodes import human_node, coordinator_router

from state import TripState

load_dotenv(override=True)

def build_graph():
    builder = StateGraph(TripState)

    builder.add_node("human", human_node)
    builder.add_node("coordinator", coordinator)
    builder.add_node("router", coordinator_router)
    builder.add_node("summarizer", summarizer)

    builder.add_edge(START, "human")

    builder.add_edge("human", "coordinator")
    builder.add_edge("coordinator", "router")
    builder.add_edge("router", "coordinator")
    builder.add_edge("summarizer", END)

    return builder.compile()


def main(max_rounds=5):
    graph = build_graph()

    print(graph.get_graph().draw_ascii())
    
    state = {}
    state = graph.invoke(state, start_at="human")

    

    for i in range(max_rounds):
        print(f"\n=== ROUND {i+1} ===")
        state = graph.invoke(state, start_at="coordinator")

        if state.get("next") == "summarizer" or "output" in state:
            if "output" not in state:
                state = graph.invoke(state, start_at="summarizer")
            break

    print("\n✅ Conversation completed.")

if __name__ == "__main__":
    main()

