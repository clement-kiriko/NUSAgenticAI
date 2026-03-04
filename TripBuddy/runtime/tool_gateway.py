from typing import Any, Dict, List

from runtime.tool_registry import ToolSpec, serialize_tool_catalog
from utils import debug


class ToolGateway:
    """Governed execution gateway for all agent tool calls."""

    def __init__(self, registry: Dict[str, ToolSpec]):
        self.registry = registry

    def discover(self, agent_name: str) -> List[Dict[str, Any]]:
        return serialize_tool_catalog(self.registry, agent_name)

    def resolve_tool_name(self, agent_name: str, capability: str) -> str:
        for spec in self.registry.values():
            if capability in spec.capabilities and agent_name in spec.allowed_agents:
                return spec.name
        raise PermissionError(f"No tool with capability '{capability}' is available to {agent_name}")

    def get_llm_schema(self, agent_name: str, tool_name: str) -> Dict[str, Any]:
        spec = self.registry.get(tool_name)
        if not spec:
            raise KeyError(f"Unknown tool: {tool_name}")
        if agent_name not in spec.allowed_agents:
            raise PermissionError(f"{agent_name} is not allowed to use {tool_name}")
        if not spec.llm_schema:
            raise ValueError(f"Tool {tool_name} has no LLM schema")
        return spec.llm_schema

    def invoke(self, state: dict, agent_name: str, tool_name: str, *args, **kwargs):
        spec = self.registry.get(tool_name)
        if not spec:
            raise KeyError(f"Unknown tool: {tool_name}")
        if agent_name not in spec.allowed_agents:
            raise PermissionError(f"{agent_name} is not allowed to call {tool_name}")

        result = spec.handler(*args, **kwargs)
        debug(f"{agent_name} -> {tool_name} args={list(args)} kwargs={kwargs}", prefix="TOOL")
        debug(f"{tool_name} result preview: {str(result)[:260]}", prefix="TOOL")
        state.setdefault("tool_calls", []).append(
            {"agent": agent_name, "tool": tool_name, "args": list(args), "kwargs": kwargs}
        )
        return result

    def invoke_capability(self, state: dict, agent_name: str, capability: str, *args, **kwargs):
        tool_name = self.resolve_tool_name(agent_name, capability)
        return self.invoke(state, agent_name, tool_name, *args, **kwargs)
