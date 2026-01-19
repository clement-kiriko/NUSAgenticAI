from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
import json



def destination(state):
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)
    trips_json = json.dumps(state.get("trip_options", []), indent=2)
    convo = "\n".join(f"{r}: {m}" for r, m in state.get("conversation", []))

    sys = "You are the Senior Destination Expert. Pick the best option and explain briefly."
    user = f"Trip options:\n{trips_json}\n\nConversation:\n{convo}"

    res = llm.invoke([SystemMessage(content=sys), HumanMessage(content=user)]).content
    print(f"🏝️ Destination Expert: {res[:120]}...")
    state["conversation"].append(("destination_expert", res))
    state["destination_done"] = True
    return state
