"""
Standalone test for the food_agent.

Runs the agent against a few Southeast Asia / Japan destinations and
prints the resulting food plan for each. No other agents are invoked.

Usage (from TripBuddy/):
    python -m pytest tests/test_food_agent.py -v -s
  or simply:
    python tests/test_food_agent.py
"""
import json
import sys
import os

# Ensure the TripBuddy package root is on the path when run directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

import pytest
from agents.food import food_agent


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_state(location: str, days: int = 4, budget_sgd: int = 2000) -> dict:
    """Build a minimal TripState for the food agent."""
    return {
        "user_requirements": {
            "location_preference": location,
            "days": days,
            "budget_sgd": budget_sgd,
            "travellers": 2,
            "dietary_restrictions": [],
        },
        "feedback": "",
        "optimization_hints": {},
        "conversation": [],
        "tool_calls": [],
    }


def _assert_plan(plan: dict, location: str):
    """Assert that the food plan has the expected top-level keys."""
    assert isinstance(plan, dict), f"[{location}] food_plan is not a dict"
    missing = [k for k in ("meal_plan", "dietary_notes", "top_food_spots", "estimated_total_sgd") if k not in plan]
    assert not missing, f"[{location}] food_plan missing keys: {missing}"
    assert plan["estimated_total_sgd"] >= 0, f"[{location}] negative cost"
    print(f"\n{'='*60}")
    print(f"Location : {location}")
    print(json.dumps(plan, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

LOCATIONS = [
    ("Tenjin, Fukuoka, Japan",          5),
    ("Shibuya, Tokyo, Japan",           3),
    ("Orchard Road, Singapore",         4),
    ("Chatuchak, Bangkok, Thailand",    6),
    ("Old Quarter, Hanoi, Vietnam",     4),
]


@pytest.mark.parametrize("location,days", LOCATIONS)
def test_food_agent(location: str, days: int):
    state = _make_state(location, days=days)
    result = food_agent(state)

    assert "food_plan" in result, f"[{location}] food_plan key missing from state"
    _assert_plan(result["food_plan"], location)

    # Confirm tool_calls were recorded
    tool_names = [t["tool"] for t in result.get("tool_calls", [])]
    assert "FoodAPI" in tool_names, f"[{location}] FoodAPI not recorded in tool_calls"

    # Confirm agent appended to conversation
    speakers = [s for s, _ in result.get("conversation", [])]
    assert "food_agent" in speakers, f"[{location}] food_agent not in conversation"


# ---------------------------------------------------------------------------
# Direct run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    for location, days in LOCATIONS:
        print(f"\nTesting: {location} ({days} days)")
        state = _make_state(location, days=days)
        try:
            result = food_agent(state)
            _assert_plan(result["food_plan"], location)
            print("PASS")
        except Exception as exc:
            print(f"FAIL – {exc}")
