from prometheus_client import Counter, Histogram


HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests served by the API.",
    ["method", "path", "status_code"],
)

HTTP_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds.",
    ["method", "path", "status_code"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)


AGENT_TOOL_CALLS = Counter(
    "agent_tool_calls_total",
    "Total tool calls executed through the tool gateway.",
    ["agent_name", "tool_name"],
)

AGENT_LATENCY = Histogram(
    "agent_execution_seconds",
    "Time spent executing planner steps, tool calls, and planner runs.",
    ["agent_name"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)

LLM_TOKENS_TOTAL = Counter(
    "llm_tokens_total",
    "Total LLM tokens consumed.",
    ["model", "token_type"],
)
