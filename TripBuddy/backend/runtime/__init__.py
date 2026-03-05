from runtime.llm_router import LLMRouter
from runtime.tool_gateway import ToolGateway
from runtime.tool_registry import build_tool_registry

TOOL_REGISTRY = build_tool_registry()
TOOL_GATEWAY = ToolGateway(TOOL_REGISTRY)
LLM_ROUTER = LLMRouter()

__all__ = [
    "TOOL_REGISTRY",
    "TOOL_GATEWAY",
    "LLM_ROUTER",
]
