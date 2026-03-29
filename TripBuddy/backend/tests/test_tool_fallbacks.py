import os
import sys
from unittest.mock import patch

import pytest
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _minimal_state() -> dict:
    return {
        "tool_calls": [],
        "conversation": [],
        "feedback": "",
        "round_number": 0,
        "optimization_hints": {},
    }


def test_flight_api_returns_fallback_when_api_key_missing():
    from tools.aviationstack_api import flight_api

    with patch.dict(os.environ, {"AVIATIONSTACK_API_KEY": ""}, clear=False):
        result = flight_api("SIN", "TYO", 3)

    assert result == []


def test_flight_api_returns_fallback_on_request_exception():
    from tools.aviationstack_api import flight_api

    with patch.dict(os.environ, {"AVIATIONSTACK_API_KEY": "12345678"}, clear=False):
        with patch("tools.aviationstack_api.requests.get", side_effect=requests.RequestException("timeout")):
            result = flight_api("SIN", "TYO", 3)

    assert result == []


def test_tool_gateway_returns_fallback_instead_of_raising():
    from runtime.tool_registry import build_tool_registry
    from runtime.tool_gateway import ToolGateway

    registry = build_tool_registry()
    gateway = ToolGateway(registry)
    state = _minimal_state()

    with patch("runtime.tool_gateway.timed_agent_call", side_effect=RuntimeError("boom")):
        result = gateway.invoke_capability(state, "flight_agent", "flight_search", "SIN", "TYO", 3)

    assert result == []
    assert len(state["tool_calls"]) == 1
    assert state["tool_calls"][0]["status"] == "error"
    assert any("fallback response applied" in entry["summary"].lower() for entry in state.get("decision_trace", []))


def test_food_live_search_returns_empty_list_when_geocode_fails():
    from tools.services.food_service import search_food_live

    with patch("tools.services.food_service.nominatim_geocode", return_value=None):
        result = search_food_live("unknown place", radius_m=500, limit=5)

    assert result == []
