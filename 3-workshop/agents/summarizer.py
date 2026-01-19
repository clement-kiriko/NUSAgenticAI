from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
import json

def summarizer(state):
    print(f"🧭 Summarizer Agent Running")
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)
    convo = "\n".join(f"{r}: {m}" for r, m in state.get("conversation", []))
    sys = ("You are the Summarizer Node. Output ONLY JSON with keys:\n"
           "{ 'destination': '', 'budget': '', 'itinerary': '', 'summary': '' }")
    res = llm.invoke([SystemMessage(content=sys), HumanMessage(content=convo)]).content

    try:
        data = json.loads(res)
    except json.JSONDecodeError:
        data = {"destination": "N/A", "budget": "N/A", "itinerary": "N/A", "summary": res}

    print("\n=== Final Trip Plan ===")
    print(f"Destination: {data.get('destination','N/A')}")
    print(f"Budget: {data.get('budget','N/A')}")
    print(f"Itinerary: {data.get('itinerary','N/A')}")
    print(f"Summary: {data.get('summary','N/A')}")
    state["final_summary"] = data
    return {"output": data}
