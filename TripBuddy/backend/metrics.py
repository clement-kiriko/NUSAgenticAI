from prometheus_client import Counter, Histogram


AGENT_TOOL_CALLS = Counter(
    "agent_tool_calls_total",
    "Total tool calls executed through the tool gateway.",
    ["agent_name", "tool_name"],
)

AGENT_LATENCY = Histogram(
    "agent_execution_seconds",
    "Time spent executing planner steps, tool calls, and planner runs.",
    ["agent_name"],
)

LLM_TOKENS_TOTAL = Counter(
    "llm_tokens_total",
    "Total LLM tokens consumed.",
    ["model", "token_type"],
)
