import time
from contextlib import contextmanager
from typing import Any, Callable, Iterator

from monitoring.metrics import (
    AGENT_LATENCY,
    AGENT_TOOL_CALLS,
    HTTP_REQUEST_DURATION,
    HTTP_REQUESTS_TOTAL,
    LLM_TOKENS_TOTAL,
)


@contextmanager
def observe_agent_latency(agent_name: str) -> Iterator[None]:
    started_at = time.perf_counter()
    try:
        yield
    finally:
        AGENT_LATENCY.labels(agent_name=agent_name).observe(time.perf_counter() - started_at)


def timed_agent_call(agent_name: str, fn: Callable[..., Any], *args, **kwargs):
    with observe_agent_latency(agent_name):
        return fn(*args, **kwargs)


def record_tool_call(agent_name: str, tool_name: str) -> None:
    AGENT_TOOL_CALLS.labels(agent_name=agent_name, tool_name=tool_name).inc()


def record_http_request(method: str, path: str, status_code: str, duration_seconds: float) -> None:
    HTTP_REQUESTS_TOTAL.labels(method=method, path=path, status_code=status_code).inc()
    HTTP_REQUEST_DURATION.labels(method=method, path=path, status_code=status_code).observe(duration_seconds)


def record_llm_token_usage(model: str, usage: Any) -> None:
    if not usage:
        return

    token_values = {
        "prompt": getattr(usage, "prompt_tokens", 0) or 0,
        "completion": getattr(usage, "completion_tokens", 0) or 0,
        "total": getattr(usage, "total_tokens", 0) or 0,
    }
    for token_type, value in token_values.items():
        if value:
            LLM_TOKENS_TOTAL.labels(model=model, token_type=token_type).inc(value)
