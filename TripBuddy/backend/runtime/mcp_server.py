import json
import sys
import traceback
from typing import Any, Dict, List

from runtime import TOOL_GATEWAY, TOOL_REGISTRY


class MCPServer:
    """Minimal stdio MCP-compatible server adapter over Tool Registry/Gateway."""

    def __init__(self):
        self.server_info = {"name": "tripbuddy-mcp", "version": "0.1.0"}

    def _jsonrpc_result(self, req_id: Any, result: Dict[str, Any]) -> Dict[str, Any]:
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    def _jsonrpc_error(self, req_id: Any, code: int, message: str, data: Any = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}
        if data is not None:
            payload["error"]["data"] = data
        return payload

    def _tool_input_schema(self, tool_name: str) -> Dict[str, Any]:
        spec = TOOL_REGISTRY[tool_name]
        if spec.llm_schema and "function" in spec.llm_schema:
            params = spec.llm_schema["function"].get("parameters")
            if isinstance(params, dict):
                return params
        return {"type": "object", "properties": {}, "additionalProperties": True}

    def _list_tools(self, agent_name: str | None = None) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for spec in TOOL_REGISTRY.values():
            if agent_name and agent_name not in spec.allowed_agents:
                continue
            rows.append(
                {
                    "name": spec.name,
                    "description": spec.description,
                    "inputSchema": self._tool_input_schema(spec.name),
                    "x-allowedAgents": sorted(spec.allowed_agents),
                    "x-capabilities": sorted(spec.capabilities),
                }
            )
        return rows

    def _handle_initialize(self, req_id: Any) -> Dict[str, Any]:
        return self._jsonrpc_result(
            req_id,
            {
                "protocolVersion": "2024-11-05",
                "serverInfo": self.server_info,
                "capabilities": {"tools": {"listChanged": False}},
            },
        )

    def _handle_tools_list(self, req_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
        agent_name = params.get("agent_name")
        return self._jsonrpc_result(req_id, {"tools": self._list_tools(agent_name=agent_name)})

    def _handle_tools_call(self, req_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments", {})
        agent_name = params.get("agent_name")

        if not isinstance(name, str) or not name:
            return self._jsonrpc_error(req_id, -32602, "Invalid params: 'name' is required.")
        if not isinstance(arguments, dict):
            return self._jsonrpc_error(req_id, -32602, "Invalid params: 'arguments' must be an object.")
        if not isinstance(agent_name, str) or not agent_name:
            return self._jsonrpc_error(
                req_id,
                -32602,
                "Invalid params: 'agent_name' is required for permission-aware tool execution.",
            )

        try:
            # External tool calls do not mutate workflow state; keep lightweight audit object.
            local_state: Dict[str, Any] = {"tool_calls": []}
            result = TOOL_GATEWAY.invoke(local_state, agent_name, name, **arguments)
            return self._jsonrpc_result(
                req_id,
                {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result, ensure_ascii=True),
                        }
                    ],
                    "isError": False,
                    "x-toolCalls": local_state.get("tool_calls", []),
                },
            )
        except Exception as exc:  # noqa: BLE001
            return self._jsonrpc_result(
                req_id,
                {
                    "content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}],
                    "isError": True,
                },
            )

    def handle(self, request: Dict[str, Any]) -> Dict[str, Any] | None:
        method = request.get("method")
        req_id = request.get("id")
        params = request.get("params", {}) or {}

        if method == "initialize":
            return self._handle_initialize(req_id)
        if method == "tools/list":
            return self._handle_tools_list(req_id, params)
        if method == "tools/call":
            return self._handle_tools_call(req_id, params)
        if method == "notifications/initialized":
            return None
        return self._jsonrpc_error(req_id, -32601, f"Method not found: {method}")


def run_stdio_server() -> None:
    server = MCPServer()
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                raise ValueError("JSON-RPC request must be an object")
            response = server.handle(request)
            if response is not None:
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
        except Exception as exc:  # noqa: BLE001
            err = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32700,
                    "message": f"Parse/handle error: {exc}",
                    "data": traceback.format_exc(limit=1),
                },
            }
            sys.stdout.write(json.dumps(err) + "\n")
            sys.stdout.flush()
