from agents.orchestrator import call_tool_by_capability
from .agent_policy import AGENT_TOOL_POLICY

def safe_tool_call(state, agent, capability, *args):

    allowed = AGENT_TOOL_POLICY.get(agent, set())

    if capability not in allowed:
        raise PermissionError(
            f"{agent} attempted unauthorized tool: {capability}"
        )

    return call_tool_by_capability(state, agent, capability, *args)