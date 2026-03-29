"""
Unit tests for TripBuddy backend – pure functions and mocked paths.

These tests do NOT call the LLM or external APIs. Any function that
touches the network has its dependencies mocked away.

Run from TripBuddy/backend/:
    pytest tests/test_backend.py -v
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers shared across tests
# ---------------------------------------------------------------------------

def _minimal_state(**overrides) -> dict:
    """Return a minimal valid TripState dict."""
    state = {
        "user_requirements": {
            "days": 3,
            "budget_sgd": 1500.0,
            "location_preference": "Tokyo, Japan",
            "start_date": "2026-06-01",
            "end_date": "2026-06-03",
            "dietary_restrictions": "none",
        },
        "feedback": "",
        "satisfied": False,
        "auto_rerun": False,
        "round_number": 0,
        "max_rounds": 3,
        "optimization_hints": {},
        "tool_calls": [],
        "conversation": [],
    }
    state.update(overrides)
    return state


# ===========================================================================
# planner.py – pure helpers
# ===========================================================================

class TestHasValue:
    """Tests for planner._has_value (private, imported directly)."""

    def setup_method(self):
        from planner import _has_value
        self.fn = _has_value

    def test_none_is_falsy(self):
        assert self.fn(None) is False

    def test_empty_string_is_falsy(self):
        assert self.fn("") is False

    def test_whitespace_string_is_falsy(self):
        assert self.fn("   ") is False

    def test_non_empty_string_is_truthy(self):
        assert self.fn("Tokyo") is True

    def test_empty_list_is_falsy(self):
        assert self.fn([]) is False

    def test_non_empty_list_is_truthy(self):
        assert self.fn(["item"]) is True

    def test_empty_dict_is_falsy(self):
        assert self.fn({}) is False

    def test_non_empty_dict_is_truthy(self):
        assert self.fn({"key": "value"}) is True

    def test_zero_int_is_truthy(self):
        # 0 is not None / empty string / empty container
        assert self.fn(0) is True

    def test_positive_int_is_truthy(self):
        assert self.fn(42) is True


class TestMissingCriticalFields:
    """Tests for planner._missing_critical_fields."""

    def setup_method(self):
        from planner import _missing_critical_fields
        self.fn = _missing_critical_fields

    def _complete_state(self) -> dict:
        return {
            "flight_plan":       {"selected_option": "SQ123"},
            "locations_plan":    {"top_attractions": ["Shibuya"]},
            "food_plan":         {"meal_plan": "Ramen for dinner"},
            "accomodations_plan":{"selected_stay": "Hotel A"},
            "budget_plan":       {"projected_total_sgd": 1200, "within_budget": True},
            "report": {
                "overview":          "Day 1: ...",
                "recommendations":   ["book early"],
                "budget_summary":    "Under budget",
            },
        }

    def test_complete_state_has_no_missing_fields(self):
        assert self.fn(self._complete_state()) == []

    def test_missing_flight_selected_option(self):
        state = self._complete_state()
        state["flight_plan"]["selected_option"] = None
        missing = self.fn(state)
        assert "flight.selected_option" in missing

    def test_missing_top_attractions(self):
        state = self._complete_state()
        state["locations_plan"]["top_attractions"] = []
        missing = self.fn(state)
        assert "locations.top_attractions" in missing

    def test_missing_food_meal_plan(self):
        state = self._complete_state()
        state["food_plan"]["meal_plan"] = ""
        missing = self.fn(state)
        assert "food.meal_plan" in missing

    def test_missing_accomodations_selected_stay(self):
        state = self._complete_state()
        state["accomodations_plan"]["selected_stay"] = None
        missing = self.fn(state)
        assert "accomodations.selected_stay" in missing

    def test_missing_projected_total(self):
        state = self._complete_state()
        del state["budget_plan"]["projected_total_sgd"]
        missing = self.fn(state)
        assert "budget.projected_total_sgd" in missing

    def test_missing_within_budget_key(self):
        state = self._complete_state()
        del state["budget_plan"]["within_budget"]
        missing = self.fn(state)
        assert "budget.within_budget" in missing

    def test_missing_report_overview(self):
        state = self._complete_state()
        state["report"]["overview"] = ""
        missing = self.fn(state)
        assert "report.overview" in missing

    def test_empty_state_returns_all_missing(self):
        missing = self.fn({})
        # All critical fields should be reported missing
        assert len(missing) >= 7

    def test_multiple_fields_missing_at_once(self):
        state = self._complete_state()
        state["flight_plan"]["selected_option"] = None
        state["food_plan"]["meal_plan"] = ""
        missing = self.fn(state)
        assert "flight.selected_option" in missing
        assert "food.meal_plan" in missing


class TestShouldAutoRerun:
    """Tests for planner._should_auto_rerun."""

    def setup_method(self):
        from planner import _should_auto_rerun
        self.fn = _should_auto_rerun

    def _state(self, within_budget: bool, round_number: int, max_rounds: int,
               complete: bool = True) -> dict:
        budget_plan = {"within_budget": within_budget, "projected_total_sgd": 1000}
        if complete:
            return {
                "budget_plan": budget_plan,
                "round_number": round_number,
                "max_rounds": max_rounds,
                "flight_plan":        {"selected_option": "SQ1"},
                "locations_plan":     {"top_attractions": ["X"]},
                "food_plan":          {"meal_plan": "Plan"},
                "accomodations_plan": {"selected_stay": "Hotel X"},
                "report": {
                    "overview": "Overview",
                    "recommendations": ["R"],
                    "budget_summary": "Summary",
                },
            }
        return {"budget_plan": budget_plan, "round_number": round_number, "max_rounds": max_rounds}

    def test_within_budget_and_complete_no_rerun(self):
        should, missing, within = self.fn(self._state(True, 1, 3, complete=True))
        assert should is False
        assert within is True
        assert missing == []

    def test_over_budget_triggers_rerun(self):
        should, missing, within = self.fn(self._state(False, 1, 3, complete=True))
        assert should is True
        assert within is False

    def test_reached_max_rounds_no_rerun(self):
        should, _, _ = self.fn(self._state(False, 3, 3, complete=True))
        assert should is False

    def test_missing_fields_triggers_rerun_even_if_within_budget(self):
        state = self._state(True, 1, 3, complete=False)
        should, missing, _ = self.fn(state)
        assert should is True
        assert len(missing) > 0

    def test_round_less_than_max_and_over_budget(self):
        should, _, _ = self.fn(self._state(False, 2, 3, complete=True))
        assert should is True


class TestBuildInitialState:
    """Tests for planner.build_initial_state."""

    def setup_method(self):
        from planner import build_initial_state
        self.fn = build_initial_state

    def _requirements(self, **overrides) -> dict:
        req = {
            "days": "3",
            "budget_sgd": "2000",
            "country": "Japan",
            "city": "",
            "start_date": "2026-06-01",
            "dietary_restrictions": "vegetarian",
        }
        req.update(overrides)
        return req

    def test_days_coerced_to_int(self):
        state = self.fn(self._requirements())
        assert isinstance(state["user_requirements"]["days"], int)
        assert state["user_requirements"]["days"] == 3

    def test_budget_coerced_to_float(self):
        state = self.fn(self._requirements())
        assert isinstance(state["user_requirements"]["budget_sgd"], float)

    def test_end_date_computed_correctly(self):
        state = self.fn(self._requirements(days="3", start_date="2026-06-01"))
        # 3 days starting 2026-06-01 → last day is 2026-06-03
        assert state["user_requirements"]["end_date"] == "2026-06-03"

    def test_single_day_trip_end_equals_start(self):
        state = self.fn(self._requirements(days="1", start_date="2026-08-15"))
        assert state["user_requirements"]["end_date"] == "2026-08-15"

    def test_dietary_restrictions_preserved(self):
        state = self.fn(self._requirements(dietary_restrictions="vegan"))
        assert state["user_requirements"]["dietary_restrictions"] == "vegan"

    def test_missing_dietary_restrictions_defaults_to_none(self):
        req = self._requirements()
        del req["dietary_restrictions"]
        state = self.fn(req)
        assert state["user_requirements"]["dietary_restrictions"] == "none"

    def test_empty_dietary_restrictions_defaults_to_none(self):
        state = self.fn(self._requirements(dietary_restrictions=""))
        assert state["user_requirements"]["dietary_restrictions"] == "none"

    def test_round_number_starts_at_zero(self):
        state = self.fn(self._requirements())
        assert state["round_number"] == 0

    def test_max_rounds_default_is_three(self):
        state = self.fn(self._requirements())
        assert state["max_rounds"] == 3

    def test_conversation_contains_intake_entry(self):
        state = self.fn(self._requirements())
        speakers = [s for s, _ in state["conversation"]]
        assert "human_intake" in speakers

    def test_city_is_preserved_when_provided(self):
        state = self.fn(self._requirements(city="Tokyo"))
        assert state["user_requirements"]["city"] == "Tokyo"
        assert state["user_requirements"]["country"] == "Japan"

    def test_location_preference_uses_city_and_country_when_city_present(self):
        state = self.fn(self._requirements(city="Tokyo"))
        assert state["user_requirements"]["location_preference"] == "Tokyo, Japan"

    def test_location_preference_falls_back_to_country_when_city_missing(self):
        state = self.fn(self._requirements(city=""))
        assert state["user_requirements"]["location_preference"] == "Japan"


class TestReportToMarkdown:
    """Tests for planner.report_to_markdown."""

    def setup_method(self):
        from planner import report_to_markdown
        self.fn = report_to_markdown

    def test_starts_with_trip_plan_report_header(self):
        result = self.fn({})
        assert result.startswith("# Trip Plan Report")

    def test_overview_section_included(self):
        result = self.fn({"overview": "Day 1: Explore Tokyo"})
        assert "## Overview" in result
        assert "Day 1: Explore Tokyo" in result

    def test_recommendations_list_rendered(self):
        result = self.fn({"recommendations": ["Book early", "Use JR Pass"]})
        assert "## Recommendations" in result
        assert "Book early" in result
        assert "JR Pass" in result

    def test_budget_summary_dict_rendered(self):
        result = self.fn({"budget_summary": {"flights": "SGD 500", "hotel": "SGD 300"}})
        assert "## Budget Summary" in result
        assert "SGD 500" in result

    def test_missing_section_not_in_output(self):
        result = self.fn({"overview": "Brief overview"})
        assert "## Recommendations" not in result

    def test_empty_report_returns_just_header(self):
        result = self.fn({})
        assert result == "# Trip Plan Report"

    def test_risks_section_rendered(self):
        result = self.fn({"risks": ["Typhoon season", "High tourist season"]})
        assert "## Risks" in result
        assert "Typhoon season" in result

    def test_next_iteration_focus_rendered(self):
        result = self.fn({"next_iteration_focus": ["Confirm flights"]})
        assert "## Next Iteration Focus" in result


# ===========================================================================
# agents/budget.py – _get_cost
# ===========================================================================

class TestGetCost:
    """Tests for budget._get_cost (private helper)."""

    def setup_method(self):
        from agents.budget import _get_cost
        self.fn = _get_cost

    def test_valid_integer(self):
        assert self.fn({"estimated_total_sgd": 500}) == 500.0

    def test_valid_float(self):
        assert self.fn({"estimated_total_sgd": 123.45}) == pytest.approx(123.45)

    def test_string_number(self):
        assert self.fn({"estimated_total_sgd": "250"}) == 250.0

    def test_non_numeric_string_returns_zero(self):
        assert self.fn({"estimated_total_sgd": "N/A"}) == 0.0

    def test_none_value_returns_zero(self):
        assert self.fn({"estimated_total_sgd": None}) == 0.0

    def test_missing_key_returns_zero(self):
        assert self.fn({}) == 0.0

    def test_zero_value(self):
        assert self.fn({"estimated_total_sgd": 0}) == 0.0


# ===========================================================================
# agents/budget.py – budget_agent (mocked invoke_json)
# ===========================================================================

class TestBudgetAgentFallback:
    """Tests for budget_agent deterministic fallback when invoke_json returns {}."""

    def _make_state(self, budget_sgd=2000.0, **plan_overrides) -> dict:
        state = _minimal_state()
        state["user_requirements"]["budget_sgd"] = budget_sgd
        state["flight_plan"]        = plan_overrides.get("flight_plan",        {"estimated_total_sgd": 500})
        state["food_plan"]          = plan_overrides.get("food_plan",          {"estimated_total_sgd": 300})
        state["locations_plan"]     = plan_overrides.get("locations_plan",     {"estimated_total_sgd": 200})
        state["accomodations_plan"] = plan_overrides.get("accomodations_plan", {"estimated_total_sgd": 400})
        state["conversation"] = []
        return state

    @patch("agents.budget.invoke_json", return_value={})
    def test_fallback_produces_required_keys(self, _mock):
        from agents.budget import budget_agent
        result = budget_agent(self._make_state())
        plan = result["budget_plan"]
        assert "projected_total_sgd" in plan
        assert "within_budget" in plan
        assert "buffer_sgd" in plan
        assert "adjustment_advice" in plan

    @patch("agents.budget.invoke_json", return_value={})
    def test_fallback_within_budget_true(self, _mock):
        from agents.budget import budget_agent
        # Total costs = 1400, budget = 2000
        result = budget_agent(self._make_state(budget_sgd=2000.0))
        assert result["budget_plan"]["within_budget"] is True

    @patch("agents.budget.invoke_json", return_value={})
    def test_fallback_within_budget_false(self, _mock):
        from agents.budget import budget_agent
        # Total costs = 1400, budget = 1000
        result = budget_agent(self._make_state(budget_sgd=1000.0))
        assert result["budget_plan"]["within_budget"] is False

    @patch("agents.budget.invoke_json", return_value={})
    def test_zero_budget_defaults_to_300_per_day(self, _mock):
        from agents.budget import budget_agent
        state = self._make_state(budget_sgd=0)
        result = budget_agent(state)
        # 3 days * 300 = 900 default budget
        assert result["user_requirements"]["budget_sgd"] == 900.0

    @patch("agents.budget.invoke_json", return_value={})
    def test_optimization_hints_always_set(self, _mock):
        from agents.budget import budget_agent
        result = budget_agent(self._make_state())
        hints = result.get("optimization_hints", {})
        assert "target_reduction_sgd" in hints
        assert "flight" in hints
        assert "food" in hints


# ===========================================================================
# nodes.py – feedback_router
# ===========================================================================

class TestFeedbackRouter:
    """Tests for nodes.feedback_router routing logic."""

    def setup_method(self):
        from nodes import feedback_router
        self.fn = feedback_router

    def test_auto_rerun_returns_rerun(self):
        state = _minimal_state(auto_rerun=True, satisfied=False)
        assert self.fn(state) == "rerun"

    def test_satisfied_returns_end(self):
        state = _minimal_state(auto_rerun=False, satisfied=True, round_number=1, max_rounds=3)
        assert self.fn(state) == "end"

    def test_not_satisfied_below_max_rounds_returns_rerun(self):
        state = _minimal_state(auto_rerun=False, satisfied=False, round_number=1, max_rounds=3)
        assert self.fn(state) == "rerun"

    def test_reached_max_rounds_returns_end_regardless_of_satisfied(self):
        state = _minimal_state(auto_rerun=False, satisfied=False, round_number=3, max_rounds=3)
        assert self.fn(state) == "end"

    def test_auto_rerun_takes_priority_over_satisfied(self):
        state = _minimal_state(auto_rerun=True, satisfied=True, round_number=1, max_rounds=3)
        assert self.fn(state) == "rerun"


# ===========================================================================
# nodes.py – _compute_end_date
# ===========================================================================

class TestComputeEndDate:
    """Tests for nodes._compute_end_date (private helper)."""

    def setup_method(self):
        from nodes import _compute_end_date
        self.fn = _compute_end_date

    def test_three_day_trip(self):
        assert self.fn("2026-06-01", 3) == "2026-06-03"

    def test_one_day_trip_same_day(self):
        assert self.fn("2026-06-01", 1) == "2026-06-01"

    def test_seven_day_trip(self):
        assert self.fn("2026-01-01", 7) == "2026-01-07"

    def test_month_boundary(self):
        assert self.fn("2026-01-30", 3) == "2026-02-01"

    def test_year_boundary(self):
        assert self.fn("2026-12-30", 3) == "2027-01-01"


# ===========================================================================
# tools/trip_data_tool.py – trip_data_tool
# ===========================================================================

class TestTripDataTool:
    """Tests for the static trip database lookup."""

    def setup_method(self):
        from tools.trip_data_tool import trip_data_tool
        self.fn = trip_data_tool

    def test_japan_keyword_matches(self):
        state = {"user_input": "I want to visit Japan"}
        result = self.fn(state)
        assert len(result["trip_options"]) >= 1
        countries = [t["country"] for t in result["trip_options"]]
        assert "Japan" in countries

    def test_tokyo_keyword_matches(self):
        state = {"user_input": "tokyo adventure"}
        result = self.fn(state)
        cities = [t["city"] for t in result["trip_options"]]
        assert "Tokyo" in cities

    def test_singapore_keyword_matches(self):
        state = {"user_input": "singapore trip for families"}
        result = self.fn(state)
        cities = [t["city"] for t in result["trip_options"]]
        assert "Singapore" in cities

    def test_no_match_returns_fallback(self):
        state = {"user_input": "trip to Antarctica"}
        result = self.fn(state)
        # Fallback returns first 2 entries
        assert len(result["trip_options"]) == 2

    def test_trip_options_key_always_set(self):
        state = {"user_input": ""}
        result = self.fn(state)
        assert "trip_options" in result

    def test_budget_filter_keeps_matching_trips(self):
        state = {"user_input": "japan under budget"}
        result = self.fn(state)
        assert len(result["trip_options"]) >= 1
        for trip in result["trip_options"]:
            assert trip["estimated_cost"] <= 3000


# ===========================================================================
# runtime/tool_registry.py – build_tool_registry + serialize_tool_catalog
# ===========================================================================

class TestToolRegistry:
    """Tests for the tool registry builder and catalog serialiser."""

    def setup_method(self):
        from runtime.tool_registry import build_tool_registry, serialize_tool_catalog
        self.registry = build_tool_registry()
        self.serialize = serialize_tool_catalog

    def test_registry_contains_expected_tools(self):
        expected = {"FlightAPI", "WeatherAPI", "food_catalog", "AccomsAPI",
                    "TouristAttractionAPI", "places_search", "route_estimate",
                    "place_signals", "food_search_live"}
        assert expected.issubset(set(self.registry.keys()))

    def test_flight_agent_sees_flight_search_capability(self):
        catalog = self.serialize(self.registry, "flight_agent")
        caps = {cap for row in catalog for cap in row["capabilities"]}
        assert "flight_search" in caps

    def test_flight_agent_does_not_see_food_capability(self):
        catalog = self.serialize(self.registry, "flight_agent")
        caps = {cap for row in catalog for cap in row["capabilities"]}
        assert "food_catalog" not in caps

    def test_food_agent_sees_food_catalog(self):
        catalog = self.serialize(self.registry, "food_agent")
        caps = {cap for row in catalog for cap in row["capabilities"]}
        assert "food_catalog" in caps

    def test_food_agent_does_not_see_flight_search(self):
        catalog = self.serialize(self.registry, "food_agent")
        caps = {cap for row in catalog for cap in row["capabilities"]}
        assert "flight_search" not in caps

    def test_aliases_hidden_from_catalog(self):
        # Alias entries (FoodAPI, WebSearchAPI, etc.) have no capabilities and must not appear
        catalog = self.serialize(self.registry, "food_agent")
        names = {row["name"] for row in catalog}
        assert "FoodAPI" not in names
        assert "WebSearchAPI" not in names

    def test_serialize_returns_list_of_dicts(self):
        catalog = self.serialize(self.registry, "locations_agent")
        assert isinstance(catalog, list)
        for row in catalog:
            assert isinstance(row, dict)
            assert "name" in row
            assert "description" in row
            assert "capabilities" in row

    def test_unknown_agent_gets_empty_catalog(self):
        catalog = self.serialize(self.registry, "nonexistent_agent")
        assert catalog == []

    def test_tool_spec_capabilities_is_set(self):
        spec = self.registry["FlightAPI"]
        assert isinstance(spec.capabilities, set)
        assert "flight_search" in spec.capabilities

    def test_locations_agent_sees_attraction_search(self):
        catalog = self.serialize(self.registry, "locations_agent")
        caps = {cap for row in catalog for cap in row["capabilities"]}
        assert "attraction_search" in caps
