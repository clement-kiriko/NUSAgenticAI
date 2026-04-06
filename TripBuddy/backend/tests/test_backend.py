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
import logging


# ---------------------------------------------------------------------------
# Helpers shared across tests
# ---------------------------------------------------------------------------

def _minimal_state(**overrides) -> dict:
    """Return a minimal valid TripState dict."""
    state = {
        "user_requirements": {
            "days": 3,
            "budget_sgd": 1500.0,
            "country": "Japan",
            "city": "Tokyo",
            "requested_cities": ["Tokyo"],
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


class TestAutoRerunContext:
    def setup_method(self):
        from planner import _auto_rerun_context
        self.fn = _auto_rerun_context

    def test_missing_fields_reason_is_not_budget_wording(self):
        state = _minimal_state(
            policy_evaluation={
                "assurance": {"confidence_score": 88},
                "autonomy": {"triggers": ["missing_fields"]},
            }
        )

        context = self.fn(state, ["food.meal_plan"], True)

        assert "missing_fields" in context["trigger_types"]
        assert "budget_overrun" not in context["trigger_types"]
        assert any("incomplete" in item for item in context["summary_parts"])

    def test_low_assurance_reason_is_included(self):
        state = _minimal_state(
            policy_evaluation={
                "assurance": {"confidence_score": 62},
                "autonomy": {"triggers": ["low_assurance"]},
            }
        )

        context = self.fn(state, [], True)

        assert "low_assurance" in context["trigger_types"]
        assert any("assurance confidence is low" in item for item in context["summary_parts"])


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
        assert state["user_requirements"]["requested_cities"] == ["Tokyo"]
        assert state["user_requirements"]["country"] == "Japan"

    def test_location_preference_uses_city_and_country_when_city_present(self):
        state = self.fn(self._requirements(city="Tokyo"))
        assert state["user_requirements"]["location_preference"] == "Tokyo, Japan"

    def test_location_preference_falls_back_to_country_when_city_missing(self):
        state = self.fn(self._requirements(city=""))
        assert state["user_requirements"]["location_preference"] == "Japan"


class TestApplyFeedbackUpdates:
    """Tests for planner._apply_feedback_updates."""

    def setup_method(self):
        from planner import _apply_feedback_updates
        self.fn = _apply_feedback_updates

    def test_change_city_feedback_updates_location_preference(self):
        state = _minimal_state()
        state["user_requirements"]["country"] = "Indonesia"
        state["user_requirements"]["city"] = "Bali"
        state["user_requirements"]["requested_cities"] = ["Bali"]
        state["user_requirements"]["location_preference"] = "Bali, Indonesia"

        self.fn(state, "change city to Jakarta")

        assert state["user_requirements"]["city"] == "Jakarta"
        assert state["user_requirements"]["requested_cities"] == ["Jakarta"]
        assert state["user_requirements"]["location_preference"] == "Jakarta, Indonesia"

    def test_city_assignment_feedback_strips_punctuation(self):
        state = _minimal_state()
        state["user_requirements"]["country"] = "Indonesia"
        state["user_requirements"]["city"] = "Bali"
        state["user_requirements"]["requested_cities"] = ["Bali"]
        state["user_requirements"]["location_preference"] = "Bali, Indonesia"

        self.fn(state, "city: Jakarta, please refresh the plan")

        assert state["user_requirements"]["city"] == "Jakarta"
        assert state["user_requirements"]["requested_cities"] == ["Jakarta"]
        assert state["user_requirements"]["location_preference"] == "Jakarta, Indonesia"

    def test_unrelated_feedback_does_not_change_city(self):
        state = _minimal_state()
        state["user_requirements"]["country"] = "Indonesia"
        state["user_requirements"]["city"] = "Bali"
        state["user_requirements"]["requested_cities"] = ["Bali"]
        state["user_requirements"]["location_preference"] = "Bali, Indonesia"

        self.fn(state, "make the trip cheaper")

        assert state["user_requirements"]["city"] == "Bali"
        assert state["user_requirements"]["requested_cities"] == ["Bali"]
        assert state["user_requirements"]["location_preference"] == "Bali, Indonesia"

    def test_natural_language_destination_change_is_parsed(self):
        state = _minimal_state()
        state["user_requirements"]["country"] = "Indonesia"
        state["user_requirements"]["city"] = "Bali"
        state["user_requirements"]["requested_cities"] = ["Bali"]
        state["user_requirements"]["location_preference"] = "Bali, Indonesia"

        self.fn(state, "Not Bali, I want to go to Jakarta instead")

        assert state["user_requirements"]["city"] == "Jakarta"
        assert state["user_requirements"]["requested_cities"] == ["Jakarta"]
        assert state["user_requirements"]["location_preference"] == "Jakarta, Indonesia"

    def test_multiple_cities_preserve_all_mentions_and_pick_primary_city(self):
        state = _minimal_state()
        state["user_requirements"]["country"] = "Indonesia"
        state["user_requirements"]["city"] = "Bali"
        state["user_requirements"]["requested_cities"] = ["Bali"]
        state["user_requirements"]["location_preference"] = "Bali, Indonesia"

        self.fn(state, "I want to go to Jakarta and Bandung")

        assert state["user_requirements"]["city"] == "Jakarta"
        assert state["user_requirements"]["requested_cities"] == ["Jakarta", "Bandung"]
        assert state["user_requirements"]["location_preference"] == "Jakarta, Indonesia"


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

    def test_policy_sections_rendered(self):
        result = self.fn({"assurance": {"confidence_score": 84}, "trust": {"score": 78}})
        assert "## Assurance" in result
        assert "## Trust" in result


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


class TestPolicyEngine:
    def test_decision_check_uses_matching_detail_for_boolean(self):
        from policy_engine import _decision_check

        passed = _decision_check("demo", True, pass_detail="ok", fail_detail="bad")
        failed = _decision_check("demo", False, pass_detail="ok", fail_detail="bad")

        assert passed["passed"] is True
        assert passed["detail"] == "ok"
        assert failed["passed"] is False
        assert failed["detail"] == "bad"

    def test_initialize_governance_state_sets_metadata(self):
        from policy_engine import initialize_governance_state

        state = _minimal_state()
        initialize_governance_state(state)

        assert "governance_metadata" in state
        assert state["governance_metadata"]["policy_version"]
        assert state["governance_metadata"]["audit_id"]
        assert state["governance_metadata"]["current_run_id"] == ""

    def test_evaluate_state_returns_assurance_and_fairness(self):
        from policy_engine import evaluate_state, initialize_governance_state

        state = _minimal_state(
            flight_plan={"selected_option": {"route": "SIN-TYO"}, "weather_notes": "Clear", "estimated_total_sgd": 500},
            locations_plan={"top_attractions": [{"name": "Temple", "type": "culture", "source": "geoapify"}], "estimated_total_sgd": 50},
            food_plan={"meal_plan": "Vegetarian-friendly meals", "top_food_spots": [{"name": "Cafe A", "style": "healthy", "source": "geoapify"}, {"name": "Market B", "style": "local", "source": "mock"}], "estimated_total_sgd": 120},
            accomodations_plan={"selected_stay": {"name": "Inn", "source": "geoapify"}, "estimated_total_sgd": 300},
            budget_plan={"projected_total_sgd": 970, "within_budget": True, "buffer_sgd": 530},
            report={"overview": "Trip", "recommendations": ["A"], "budget_summary": "B"},
            tool_calls=[{"tool": "FlightAPI"}, {"tool": "WeatherAPI"}, {"tool": "TouristAttractionAPI"}],
        )
        state["user_requirements"]["dietary_restrictions"] = "vegetarian"
        initialize_governance_state(state)

        evaluation = evaluate_state(state)

        assert "assurance" in evaluation
        assert "fairness" in evaluation
        assert evaluation["assurance"]["confidence_score"] >= 0
        assert evaluation["trust"]["score"] >= 0

    def test_enrich_report_adds_policy_sections(self):
        from policy_engine import enrich_report, initialize_governance_state

        state = _minimal_state(
            flight_plan={"selected_option": {"route": "SIN-TYO"}, "weather_notes": "Clear", "estimated_total_sgd": 500},
            locations_plan={"top_attractions": [{"name": "Temple", "type": "culture", "source": "geoapify"}], "estimated_total_sgd": 50},
            food_plan={"meal_plan": "Meals", "top_food_spots": [{"name": "Cafe A", "style": "healthy", "source": "geoapify"}], "estimated_total_sgd": 120},
            accomodations_plan={"selected_stay": {"name": "Inn", "source": "geoapify"}, "estimated_total_sgd": 300},
            budget_plan={"projected_total_sgd": 970, "within_budget": True, "buffer_sgd": 530},
            report={"overview": "Trip", "recommendations": ["A"], "budget_summary": "B"},
            tool_calls=[{"tool": "FlightAPI"}],
        )
        initialize_governance_state(state)

        enriched = enrich_report(state, state["report"])

        assert "governance" in enriched
        assert "assurance" in enriched
        assert "imda_alignment" in enriched
        assert "decision_trace_full" in enriched

    def test_enrich_report_summarizes_trace_but_keeps_full_trace(self):
        from policy_engine import append_decision_trace, enrich_report, initialize_governance_state

        state = _minimal_state(
            flight_plan={"selected_option": {"route": "SIN-TYO"}, "weather_notes": "Clear", "estimated_total_sgd": 500},
            locations_plan={"top_attractions": [{"name": "Temple", "type": "culture", "source": "geoapify"}], "estimated_total_sgd": 50},
            food_plan={"meal_plan": "Meals", "top_food_spots": [{"name": "Cafe A", "style": "healthy", "source": "geoapify"}], "estimated_total_sgd": 120},
            accomodations_plan={"selected_stay": {"name": "Inn", "source": "geoapify"}, "estimated_total_sgd": 300},
            budget_plan={"projected_total_sgd": 970, "within_budget": True, "buffer_sgd": 530},
            report={"overview": "Trip", "recommendations": ["A"], "budget_summary": "B"},
            tool_calls=[{"tool": "FlightAPI"}],
        )
        initialize_governance_state(state)
        append_decision_trace(state, "flight_agent", "Used governed tool FlightAPI.", outcome="success")
        append_decision_trace(state, "flight_agent", "Selected a flight strategy using flight and weather evidence.", outcome="flight_plan_ready")

        enriched = enrich_report(state, state["report"])

        assert len(enriched["decision_trace_full"]) == 2
        assert len(enriched["decision_trace"]) == 1
        assert enriched["decision_trace"][0]["stage"] == "Flights"

    def test_build_tool_audit_entry_carries_audit_id(self):
        from policy_engine import build_tool_audit_entry

        entry = build_tool_audit_entry(
            "flight_agent",
            "FlightAPI",
            ["SIN", "Tokyo"],
            {},
            audit_id="audit-123",
            run_id="run-123",
            result=[{"route": "SIN-TYO"}],
        )

        assert entry["audit_id"] == "audit-123"
        assert entry["run_id"] == "run-123"
        assert entry["tool"] == "FlightAPI"

    def test_start_new_run_updates_current_run_and_history(self):
        from policy_engine import get_run_id, initialize_governance_state, start_new_run

        state = _minimal_state()
        initialize_governance_state(state)

        run_id = start_new_run(state, "start")

        assert get_run_id(state) == run_id
        assert state["governance_metadata"]["run_history"][-1]["run_id"] == run_id
        assert state["governance_metadata"]["run_history"][-1]["mode"] == "start"

    def test_coercive_language_detail_matches_failed_status(self):
        from policy_engine import evaluate_state, initialize_governance_state

        state = _minimal_state(
            flight_plan={"selected_option": {"route": "SIN-TYO"}, "weather_notes": "Clear", "estimated_total_sgd": 500},
            locations_plan={"top_attractions": [{"name": "Temple", "type": "culture", "source": "geoapify"}], "estimated_total_sgd": 50},
            food_plan={"meal_plan": "Meals", "top_food_spots": [{"name": "Cafe A", "style": "healthy", "source": "geoapify"}], "estimated_total_sgd": 120},
            accomodations_plan={"selected_stay": {"name": "Inn", "source": "geoapify"}, "estimated_total_sgd": 300},
            budget_plan={"projected_total_sgd": 970, "within_budget": True, "buffer_sgd": 530},
            report={"overview": "Book now for the best trip."},
            tool_calls=[{"tool": "FlightAPI"}],
        )
        initialize_governance_state(state)

        evaluation = evaluate_state(state)
        coercive_check = next(item for item in evaluation["ethical_checks"]["checks"] if item["name"] == "coercive_language_absent")

        assert coercive_check["passed"] is False
        assert "detected" in coercive_check["detail"].lower()
        assert "book now" in coercive_check["detail"].lower()

    def test_budget_within_limit_detail_matches_boolean(self):
        from policy_engine import evaluate_state, initialize_governance_state

        state = _minimal_state(
            flight_plan={"selected_option": {"route": "SIN-TYO"}, "weather_notes": "Clear", "estimated_total_sgd": 100},
            locations_plan={"top_attractions": [{"name": "Temple", "type": "culture", "source": "geoapify"}], "estimated_total_sgd": 50},
            food_plan={"meal_plan": "Meals", "top_food_spots": [{"name": "Cafe A", "style": "healthy", "source": "geoapify"}], "estimated_total_sgd": 120},
            accomodations_plan={"selected_stay": {"name": "Inn", "source": "geoapify"}, "estimated_total_sgd": 200},
            budget_plan={"projected_total_sgd": 470, "within_budget": True, "buffer_sgd": 1030},
            report={"overview": "Trip"},
            tool_calls=[{"tool": "FlightAPI"}],
        )
        initialize_governance_state(state)

        evaluation = evaluate_state(state)
        budget_check = next(item for item in evaluation["assurance"]["validation_checks"] if item["name"] == "budget_within_limit")

        assert budget_check["passed"] is True
        assert "within the user's stated budget" in budget_check["detail"].lower()

    def test_fairness_checks_use_ranking_metadata(self):
        from policy_engine import evaluate_state, initialize_governance_state

        state = _minimal_state(
            flight_plan={
                "selected_option": {"route": "SIN-TYO", "is_sponsored": False},
                "weather_notes": "Clear",
                "estimated_total_sgd": 500,
                "ranking_metadata": {"selection_mode": "deterministic_stable_sort"},
            },
            locations_plan={
                "top_attractions": [{"name": "Temple", "type": "culture", "source": "geoapify", "is_sponsored": False}],
                "estimated_total_sgd": 50,
                "ranking_metadata": {"selection_mode": "deterministic_seeded_rotation"},
            },
            food_plan={
                "meal_plan": "Meals",
                "top_food_spots": [{"name": "Cafe A", "style": "healthy", "source": "geoapify", "is_sponsored": None}],
                "estimated_total_sgd": 120,
                "ranking_metadata": {"selection_mode": "deterministic_seeded_rotation"},
            },
            accomodations_plan={
                "selected_stay": {"name": "Inn", "source": "geoapify", "is_sponsored": False},
                "estimated_total_sgd": 300,
                "ranking_metadata": {"selection_mode": "deterministic_stable_sort"},
            },
            budget_plan={"projected_total_sgd": 970, "within_budget": True, "buffer_sgd": 530},
            report={"overview": "Trip"},
            tool_calls=[{"tool": "FlightAPI"}],
        )
        initialize_governance_state(state)

        evaluation = evaluate_state(state)

        fairness = {item["name"]: item for item in evaluation["fairness"]["checks"]}
        assert fairness["stable_tie_breaking"]["passed"] is True
        assert "deterministic" in fairness["stable_tie_breaking"]["detail"].lower()
        assert fairness["sponsored_bias_control"]["passed"] is True


class TestRankingModule:
    def setup_method(self):
        from ranking import rank_candidates

        self.rank_candidates = rank_candidates

    def test_same_inputs_always_produce_same_ordering(self):
        candidates = [
            {"name": "A", "ticket_sgd": 10, "type": "culture", "source": "geoapify"},
            {"name": "B", "ticket_sgd": 20, "type": "scenic", "source": "mock"},
            {"name": "C", "ticket_sgd": 15, "type": "culture", "source": "geoapify"},
        ]
        req = {"location_preference": "Tokyo, Japan", "days": 3}

        first, first_meta = self.rank_candidates(candidates, kind="location", user_requirements=req, top_k=3)
        second, second_meta = self.rank_candidates(candidates, kind="location", user_requirements=req, top_k=3)

        assert [item["id"] for item in first] == [item["id"] for item in second]
        assert first_meta["seed"] == second_meta["seed"]

    def test_sponsored_item_does_not_outrank_equivalent_non_sponsored_item(self):
        candidates = [
            {"name": "Sponsored Hotel", "nightly_rate_sgd": 100, "type": "hotel", "source": "geoapify", "is_sponsored": True},
            {"name": "Organic Hotel", "nightly_rate_sgd": 100, "type": "hotel", "source": "geoapify", "is_sponsored": False},
        ]

        ranked, _meta = self.rank_candidates(candidates, kind="accommodation", user_requirements={}, top_k=2)

        assert ranked[0]["raw"]["name"] == "Organic Hotel"

    def test_vegetarian_user_gets_tagged_food_when_available(self):
        candidates = [
            {"name": "Steak House", "cost_per_meal_sgd": 20, "style": "grill", "source": "geoapify", "dietary_tags": ["omnivore"]},
            {"name": "Green Bowl", "cost_per_meal_sgd": 20, "style": "healthy", "source": "geoapify", "dietary_tags": ["vegetarian"]},
            {"name": "Soup Spot", "cost_per_meal_sgd": 18, "style": "local", "source": "geoapify"},
        ]

        ranked, _meta = self.rank_candidates(
            candidates,
            kind="food",
            user_requirements={"dietary_restrictions": "vegetarian"},
            top_k=2,
            diversity_key="category",
        )

        assert ranked
        assert ranked[0]["raw"]["name"] == "Green Bowl"

    def test_diversity_constraints_hold_when_enough_categories_exist(self):
        candidates = [
            {"name": "Museum", "ticket_sgd": 20, "type": "culture", "source": "geoapify"},
            {"name": "Skydeck", "ticket_sgd": 20, "type": "scenic", "source": "geoapify"},
            {"name": "Old Town", "ticket_sgd": 15, "type": "culture", "source": "geoapify"},
        ]

        ranked, meta = self.rank_candidates(
            candidates,
            kind="location",
            user_requirements={"location_preference": "Tokyo, Japan"},
            top_k=2,
            diversity_key="category",
        )

        assert len(ranked) == 2
        assert len({item["category"] for item in ranked}) == 2
        assert meta["selected_count"] == 2


class TestApiServerHelpers:
    def test_audit_payload_contains_traceability_bundle(self):
        from api_server import _audit_payload, SESSION_RUNTIME
        from policy_engine import initialize_governance_state

        session_id = "session-123"
        state = _minimal_state(
            tool_calls=[{"audit_id": "audit-123", "tool": "FlightAPI"}],
            decision_trace=[{"actor": "flight_agent", "summary": "Picked flight"}],
            policy_evaluation={"assurance": {"confidence_score": 80}},
            final_report={"overview": "Trip"},
            flight_plan={"selected_option": "SQ1", "ranking_metadata": {"selection_mode": "deterministic_stable_sort", "selected_ids": ["flight:1"]}},
            locations_plan={},
            food_plan={"top_food_spots": [{"name": "Cafe A"}], "ranking_metadata": {"selection_mode": "deterministic_seeded_rotation", "selected_ids": ["food:1"]}},
            accomodations_plan={},
            budget_plan={},
        )
        initialize_governance_state(state)
        SESSION_RUNTIME[session_id] = {
            "events": [{"type": "run_started"}],
            "running": False,
            "abort_requested": False,
            "lock": __import__("threading").Lock(),
        }

        payload = _audit_payload(session_id, state)

        assert payload["session_id"] == session_id
        assert payload["audit_id"] == state["governance_metadata"]["audit_id"]
        assert "run_history" in payload
        assert payload["tool_calls"] == state["tool_calls"]
        assert payload["decision_trace_full"] == state["decision_trace"]
        assert payload["policy_evaluation"] == state["policy_evaluation"]
        assert payload["final_report"] == state["final_report"]
        assert "ranker_summary" in payload
        assert "deterministic_stable_sort" in payload["ranker_summary"]["flight"]
        assert "deterministic_seeded_rotation" in payload["ranker_summary"]["food"]

    def test_runtime_snapshot_includes_ranker_summary(self):
        from api_server import SESSION_RUNTIME, _runtime_snapshot
        from policy_engine import initialize_governance_state

        session_id = "session-456"
        state = _minimal_state(
            final_report={"overview": "Trip"},
            food_plan={
                "top_food_spots": [{"name": "Cafe A"}],
                "ranking_metadata": {"selection_mode": "deterministic_seeded_rotation", "selected_ids": ["food:1"]},
            },
        )
        initialize_governance_state(state)
        SESSION_RUNTIME[session_id] = {
            "events": [{"type": "run_started"}],
            "running": False,
            "abort_requested": False,
            "lock": __import__("threading").Lock(),
        }

        snapshot = _runtime_snapshot(session_id, state)

        assert "ranker_summary" in snapshot
        assert "food" in snapshot["ranker_summary"]
        assert "selected=1" in snapshot["ranker_summary"]["food"]


class TestLoggingSetup:
    def test_audit_formatter_omits_empty_audit_segment(self):
        from logging_setup import AuditAwareFormatter

        formatter = AuditAwareFormatter("%(levelname)s %(name)s%(audit_segment)s: %(message)s")
        record = logging.LogRecord("test.logger", logging.INFO, __file__, 1, "hello", (), None)
        record.audit_id = ""

        rendered = formatter.format(record)

        assert "[audit_id=" not in rendered

    def test_audit_formatter_includes_real_audit_id(self):
        from logging_setup import AuditAwareFormatter

        formatter = AuditAwareFormatter("%(levelname)s %(name)s%(audit_segment)s: %(message)s")
        record = logging.LogRecord("test.logger", logging.INFO, __file__, 1, "hello", (), None)
        record.audit_id = "audit-123"
        record.run_id = "run-123"

        rendered = formatter.format(record)

        assert "audit_id=audit-123" in rendered
        assert "run_id=run-123" in rendered

    def test_logging_filter_uses_contextvars_when_extra_missing(self):
        from logging_context import bind_audit_context
        from logging_setup import AuditIdFilter

        record = logging.LogRecord("tools.aviationstack_api", logging.INFO, __file__, 1, "hello", (), None)
        filt = AuditIdFilter()

        with bind_audit_context(audit_id="audit-ctx", run_id="run-ctx"):
            filt.filter(record)

        assert record.audit_id == "audit-ctx"
        assert record.run_id == "run-ctx"
