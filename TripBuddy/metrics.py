from prometheus_client import Counter, Histogram

AGENT_TOOL_CALLS = Counter("agent_tool_calls_total", "Total tool calls by agent", ["tool_name"])
AGENT_LATENCY = Histogram("agent_execution_seconds", "Time taken for agent to respond")
token_counter_total = Counter("llm_tokens_total", "Total tokens used", ["model"])
token_counter_prompt = Counter("llm_tokens_prompt", "Prompt tokens used", ["model"])
token_counter_completion = Counter("llm_tokens_completion", "Completion tokens used", ["model"])