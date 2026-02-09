from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage



def coordinator(state):
    print(f"🧭 Coordinator Running")
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)
    convo_text = "\n".join(f"{r}: {m}" for r, m in state.get("conversation", []))

    system_prompt = (
        "You are the trip coordinator. Review the conversation and decide the next step.\n"
        "Rules:\n"
        "- If the last agent's response is unclear, choose a repeat_* option.\n"
        "- If destination info missing -> destination\n"
        "- If destination done but budget missing -> budget\n"
        "- If destination+budget done but schedule missing -> scheduler\n"
        "- If all done -> summarize\n"
        "Return ONLY one token:\n"
        "destination | repeat_destination | budget | repeat_budget | "
        "scheduler | repeat_scheduler | summarize"
    )

    resp = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Conversation so far:\n{convo_text}")
    ])
    decision = (resp.content or "").strip().lower()

    if "trip_options" not in state:
        decision = "trip_tool"
    elif not state.get("destination_done"):
        decision = "destination" if "repeat" not in decision else "repeat_destination"
    elif not state.get("budget_done"):
        decision = "budget" if "repeat" not in decision else "repeat_budget"
    elif not state.get("schedule_done"):
        decision = "scheduler" if "repeat" not in decision else "repeat_scheduler"
    else:
        decision = "summarizer"

    print(f"🧭 Coordinator decided: {decision}")
    state["next"] = decision
    return state