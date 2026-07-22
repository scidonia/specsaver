"""Integration tests for the invitations example — invite + accept
sharing one three-table state, with row insertion and time-based expiry.

One parametrised test covers every Examples row of every feature file.
"""

from pathlib import Path

import pytest

from specsaver.gherkin import (
    parse_examples_tables_file,
    parse_feature_file,
    parse_rules_file,
)

EXAMPLES_DIR = Path(__file__).parent.parent / "examples" / "invitations"

FEATURES = {
    "invite.feature": (
        {
            "Happy path invite": "success",
            "Non-admin cannot invite": "error:NotAuthorizedError",
        },
        5,
    ),
    "accept.feature": (
        {
            "Happy path accept": "success",
            "Accept with wrong email is rejected": "error:EmailMismatchError",
            "Expired invitation cannot be accepted":
                "error:InvitationExpiredError",
        },
        4,
    ),
}

_RUNNER_ATTR = {
    "invite.feature": "invite_runner",
    "accept.feature": "accept_runner",
}


def _feature_path(feature: str) -> Path:
    return EXAMPLES_DIR / feature


def test_invitations_example_loads():
    import examples.invitations  # noqa: F401


@pytest.mark.parametrize("feature", sorted(FEATURES))
def test_feature_file_exists(feature):
    assert _feature_path(feature).exists()


def test_rule_blocks_are_parsed():
    for feature in FEATURES:
        rules = parse_rules_file(_feature_path(feature))
        assert len(rules) >= 1, feature


@pytest.mark.parametrize("feature", sorted(FEATURES))
def test_feature_file_parses_with_official_gherkin_parser(feature):
    outcomes, n_scenarios = FEATURES[feature]
    scenarios = parse_feature_file(_feature_path(feature))
    assert len(scenarios) == n_scenarios
    names = {s.name for s in scenarios}
    for outline in outcomes:
        assert outline in names, f"{outline} missing from {feature}"


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
    return f"{op}:{row['token']}:{row['outcome']}"


@pytest.mark.parametrize("case", _all_cases(), ids=_case_id)
def test_run_scenario_generic(case: tuple[str, dict[str, str]]):
    """One parametrised test per Examples row, dispatched by feature."""
    import examples.invitations

    feature, row = case
    runner = getattr(examples.invitations, _RUNNER_ATTR[feature])
    passed, message = runner.run(row)
    assert passed, f"Scenario failed: {message}"
