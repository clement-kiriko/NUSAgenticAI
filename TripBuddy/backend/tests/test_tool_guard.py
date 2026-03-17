# test_tool_guard.py

from backend.tools.security.tool_guard import safe_tool_call

def dummy_state():
    return {}

def test_allowed_tool():
    try:
        result = safe_tool_call(
            dummy_state(),
            "flight_agent",
            "flight_search",
            "Singapore",
            "Tokyo",
            3
        )
        print("Allowed tool call passed")
    except Exception as e:
        print("Should not fail:", e)


def test_blocked_tool():
    try:
        safe_tool_call(
            dummy_state(),
            "flight_agent",
            "delete_database"
        )
        print("Unauthorized tool NOT blocked")
    except PermissionError:
        print("Unauthorized tool correctly blocked")