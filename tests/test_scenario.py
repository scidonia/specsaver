"""Unit tests for specsaver.scenario — the SpecScenario assembler.

These exercise the assembler's Gherkin-structure handling in isolation
from any particular example (see tests/test_examples.py for the
bank_transfer integration test). Contracts are registered fresh per test
via the specsaver import machinery already loaded by conftest-free
pytest collection of the whole suite; here we only need the registry to
be queried, not populated, since these tests target structural errors
that are caught before any contract lookup succeeds.
"""

import pytest

from specsaver.scenario import GherkinStepTemplate, ScenarioSpecError, SpecScenario


def test_step_role_inherits_through_conjunctions():
    """Given steps without preconditions are allowed (they may be business
    case conditions).  Then steps without postconditions are still an
    error (spec completeness check)."""
    feature_text = """\
Feature: Widgets

  Scenario Outline: Make a widget
    Given a widget factory
    And enough raw material
    When a widget is made
    Then a widget exists
    And the material is consumed

    Examples:
      | x |
      | 1 |
"""
    with pytest.raises(ScenarioSpecError, match="no associated postcondition"):
        SpecScenario.from_text(feature_text, "widgets.feature", "Make a widget")


def test_multiple_when_steps_rejected():
    feature_text = """\
Feature: Widgets

  Scenario Outline: Two actions
    Given a widget factory
    When a widget is made
    When a second widget is made
    Then a widget exists

    Examples:
      | x |
      | 1 |
"""
    with pytest.raises(ScenarioSpecError, match="exactly one When step"):
        SpecScenario.from_text(feature_text, "widgets.feature", "Two actions")


def test_unknown_scenario_name_raises():
    feature_text = """\
Feature: Widgets

  Scenario Outline: Make a widget
    Given a widget factory
    When a widget is made
    Then a widget exists

    Examples:
      | x |
      | 1 |
"""
    with pytest.raises(ScenarioSpecError, match="No Scenario"):
        SpecScenario.from_text(feature_text, "widgets.feature", "Does not exist")


def test_gherkin_step_template_is_a_plain_value_type():
    t = GherkinStepTemplate(role="given", text="an account exists")
    assert t.role == "given"
    assert t.text == "an account exists"
