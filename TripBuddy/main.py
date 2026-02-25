from dotenv import load_dotenv
from langgraph.graph import END, START, StateGraph
from fastapi import FastAPI, Response
from prometheus_client import generate_latest
import time

app = FastAPI()

from agents import (
    accomodations_agent,
    budget_agent,
    consolidation_agent,
    flight_agent,
    food_agent,
    locations_agent,
    orchestrator_agent,
)
from nodes import feedback_node, feedback_router, intake_node
from state import TripState
from metrics import (
    AGENT_TOOL_CALLS,
    AGENT_LATENCY,
    token_counter_total,
    token_counter_prompt,
    token_counter_completion,
)

load_dotenv(override=True)





#to be added to the API calls that calls the tokens

    # usage = response['usage']
    # start_time = time.time()
    # token_counter_prompt.labels(model=request.model).inc(usage["prompt_tokens"])
    # token_counter_completion.labels(model=request.model).inc(usage["completion_tokens"])
    # token_counter_total.labels(model=request.model).inc(usage["total_tokens"])
    # AGENT_TOOL_CALLS.labels(tool_name="web_search").inc()
    # AGENT_LATENCY.observe(time.time() - start_time)


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
    app = build_graph()
    print(app.get_graph().draw_ascii())
    print("Set DEBUG=true for verbose LLM/tool trace logs.")
    start_time = time.time()
    result = app.invoke({})
    AGENT_LATENCY.observe(time.time() - start_time)
    print("\nFinal Approved Report")
    print(result.get("final_report", result.get("report")))


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type="text/plain")

if __name__ == "__main__":
    main()
