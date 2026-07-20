"""Integration tests for the inventory example — three operations sharing
one state and one invariant.

Tests use the symmetric specification-driven architecture:
  witness → materialize → context → snapshot → SpecState
  → check admissibility/invariants → execute impl
  → snapshot → check transitions/invariants

One parametrised test covers every Examples row of every feature file.
"""

from pathlib import Path

import pytest

from specsaver.gherkin import (
    parse_examples_tables_file,
    parse_feature_file,
    parse_rules_file,
)

EXAMPLES_DIR = Path(__file__).parent.parent / "examples" / "inventory"

# feature → (expected outlines → expected outcome, scenario count)
FEATURES = {
    "reserve.feature": (
        {
            "Happy path reservation": "success",
            "Insufficient stock": "error:InsufficientStockError",
            "Invalid quantity": "rejected",
            "Non-existent product": "rejected",
            "Runtime fault": "error:SimulatedFaultError",
        },
        9,
    ),
    "release.feature": (
        {
            "Happy path release": "success",
            "Release exceeds reserved": "error:ReleaseExceedsReservedError",
            "Invalid quantity": "rejected",
            "Non-existent product": "rejected",
            "Runtime fault": "error:SimulatedFaultError",
        },
        8,
    ),
    "restock.feature": (
        {
            "Happy path restock": "success",
            "Invalid quantity": "rejected",
            "Non-existent product": "rejected",
        },
        5,
    ),
}

_RUNNER_ATTR = {
    "reserve.feature": "reserve_runner",
    "release.feature": "release_runner",
    "restock.feature": "restock_runner",
}


def _feature_path(feature: str) -> Path:
    return EXAMPLES_DIR / feature


# ---------------------------------------------------------------------------
# Module loading
# ---------------------------------------------------------------------------


def test_inventory_example_loads():
    import examples.inventory  # noqa: F401


# ---------------------------------------------------------------------------
# Feature file parsing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("feature", sorted(FEATURES))
def test_feature_file_exists(feature):
    assert _feature_path(feature).exists()


def test_rule_blocks_are_parsed():
    for feature in FEATURES:
        rules = parse_rules_file(_feature_path(feature))
        texts = {r.text for r in rules}
        assert (
            "Reserved stock never exceeds physical stock at all times" in texts
        ), feature


@pytest.mark.parametrize("feature", sorted(FEATURES))
def test_feature_file_parses_with_official_gherkin_parser(feature):
    outcomes, n_scenarios = FEATURES[feature]
    scenarios = parse_feature_file(_feature_path(feature))
    assert len(scenarios) == n_scenarios
    names = {s.name for s in scenarios}
    for outline in outcomes:
        assert outline in names, f"{outline} missing from {feature}"


@pytest.mark.parametrize("feature", sorted(FEATURES))
def test_scenario_outlines_have_no_leftover_placeholders(feature):
    scenarios = parse_feature_file(_feature_path(feature))
    for scenario in scenarios:
        for step in scenario.steps:
            assert "<" not in step.text or ">" not in step.text


@pytest.mark.parametrize("feature", sorted(FEATURES))
def test_examples_tables_are_structured_not_text(feature):
    outcomes, _ = FEATURES[feature]
    tables = parse_examples_tables_file(_feature_path(feature))
    assert len(tables) == len(outcomes)
    assert all(t.table_name == "Examples" for t in tables)


@pytest.mark.parametrize("feature", sorted(FEATURES))
def test_every_examples_row_has_an_outcome(feature):
    outcomes, _ = FEATURES[feature]
    tables = parse_examples_tables_file(_feature_path(feature))
    seen = set()
    for table in tables:
        assert "outcome" in table.columns
        expected = outcomes[table.outline_name]
        for row in table.rows:
            assert row["outcome"] == expected
        seen.add(table.outline_name)
    assert seen == set(outcomes)


# ---------------------------------------------------------------------------
# Symmetric scenario runner — all rows of all features
# ---------------------------------------------------------------------------


def _all_cases() -> list[tuple[str, dict[str, str]]]:
    cases: list[tuple[str, dict[str, str]]] = []
    for feature, (outcomes, _) in FEATURES.items():
        tables = parse_examples_tables_file(_feature_path(feature))
        for t in tables:
            if t.outline_name in outcomes:
                cases.extend((feature, row) for row in t.rows)
    return cases


def _case_id(case: tuple[str, dict[str, str]]) -> str:
    feature, row = case
    op = feature.split(".")[0]
    order = row.get("order", "-")
    return f"{op}:{row['sku']}:{order}:{row['quantity']}:{row['outcome']}"


@pytest.mark.parametrize("case", _all_cases(), ids=_case_id)
def test_run_scenario_generic(case: tuple[str, dict[str, str]]):
    """One parametrised test per Examples row, dispatched by feature.
    Uses the contract.Contract from the domain package."""
    import examples.inventory

    feature, row = case
    runner = getattr(examples.inventory, _RUNNER_ATTR[feature])
    passed, message = runner.run(row)
    assert passed, f"Scenario failed: {message}"
