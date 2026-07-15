"""Integration tests for the bank transfer example.

Tests use the symmetric specification-driven architecture:
  witness → materialize → context → snapshot → SpecState
  → check admissibility/invariants → execute impl
  → snapshot → check transitions/invariants

One parametrised test covers every Examples row.  No hand-written
assertions beyond wiring witness/materializer/projection/impl.
"""

from pathlib import Path

import pytest

from specsaver import (
    ContractKind,
    SpecScenario,
    get_registry,
)
from specsaver.gherkin import (
    examples_for,
    parse_examples_tables_file,
    parse_feature_file,
    parse_rules_file,
)

FEATURE_PATH = (
    Path(__file__).parent.parent / "examples" / "bank_transfer" / "transfer.feature"
)
FEATURE = "transfer.feature"


# ---------------------------------------------------------------------------
# Module loading & registry shape
# ---------------------------------------------------------------------------


def test_bank_transfer_example_loads():
    import examples.bank_transfer  # noqa: F401


def test_all_contracts_registered():
    import examples.bank_transfer  # noqa: F401

    registry = get_registry()
    preconds = registry.list_by_feature_and_kind(FEATURE, ContractKind.PRECONDITION)
    assert len(preconds) == 3, f"Expected 3 preconditions, got {len(preconds)}"

    postconds = registry.list_by_feature_and_kind(FEATURE, ContractKind.POSTCONDITION)
    assert len(postconds) == 5, f"Expected 5 postconditions, got {len(postconds)}"

    invariants = registry.list_by_feature_and_kind(FEATURE, ContractKind.INVARIANT)
    assert len(invariants) == 1, f"Expected 1 invariant, got {len(invariants)}"


def test_contracts_declare_feature_file():
    import examples.bank_transfer  # noqa: F401

    registry = get_registry()
    records = registry.list_by_module("examples.bank_transfer.contracts")
    with_feature = [r for r in records if r.feature == FEATURE]
    assert len(with_feature) >= 12


# ---------------------------------------------------------------------------
# Predicates
# ---------------------------------------------------------------------------


def test_predicates_execute():
    from examples.bank_transfer import (
        Account,
        TransferDerived,
        TransferObserved,
        TransferSpecState,
        account_exists,
        has_sufficient_funds,
        is_sorted_within,
        same_currency,
    )

    state = TransferSpecState(
        observed=TransferObserved(
            accounts={
                "a1": Account(id="a1", balance=100, currency="USD"),
                "a2": Account(id="a2", balance=50, currency="USD"),
            }
        ),
        derived=TransferDerived(total_balance=150),
    )

    assert account_exists(state, "a1")
    assert not account_exists(state, "a3")
    assert has_sufficient_funds(state, "a1", 50)
    assert not has_sufficient_funds(state, "a1", 200)
    assert same_currency(state, "a1", "a2")

    assert is_sorted_within([1, 2, 3, 4], 0, 3)
    assert not is_sorted_within([1, 3, 2, 4], 0, 3)


# ---------------------------------------------------------------------------
# Direct contract calls
# ---------------------------------------------------------------------------


def test_invariant():
    from examples.bank_transfer import (
        Account,
        TransferDerived,
        TransferObserved,
        TransferSpecState,
        account_balance_non_negative,
    )

    good = TransferSpecState(
        observed=TransferObserved(
            accounts={
                "a1": Account(id="a1", balance=100, currency="USD"),
                "a2": Account(id="a2", balance=0, currency="USD"),
            }
        ),
        derived=TransferDerived(total_balance=100),
    )
    assert account_balance_non_negative(good)

    bad = TransferSpecState(
        observed=TransferObserved(
            accounts={"a1": Account(id="a1", balance=-5, currency="USD")}
        ),
        derived=TransferDerived(total_balance=-5),
    )
    assert not account_balance_non_negative(bad)


def test_frame_and_effect():
    from examples.bank_transfer import (
        transfer_effect,
        transfer_reads_frame,
        transfer_writes_frame,
    )
    from specsaver.types import Field

    writes = transfer_writes_frame()
    assert Field("source.balance") in writes.writes
    assert Field("target.balance") in writes.writes

    reads = transfer_reads_frame()
    assert Field("source.balance") in reads.reads

    eff = transfer_effect()
    assert "database" in eff.uses
    assert any(e.name == "audit.transfer_completed" for e in eff.emits)


# ---------------------------------------------------------------------------
# Gherkin → Contract traceability
# ---------------------------------------------------------------------------


def test_contracts_carry_gherkin_origin():
    import examples.bank_transfer  # noqa: F401

    registry = get_registry()
    derived = registry.list_by_gherkin(
        "the total balance across all accounts is unchanged"
    )
    assert len(derived) >= 1
    assert any("transfer_post_total_preserved" in r.identifier for r in derived)


def test_gherkin_step_resolves_to_contracts():
    import examples.bank_transfer  # noqa: F401

    registry = get_registry()
    given_step = (
        'an account "<source>" with balance <source_balance>'
        ' in currency "<source_currency>"'
    )
    derived = registry.list_by_gherkin(given_step)
    preconds = [r for r in derived if r.kind == ContractKind.PRECONDITION]
    assert len(preconds) == 1, (
        f"'{given_step}' should resolve to exactly 1 precondition "
        f"(source_exists), got {len(preconds)}: "
        f"{[r.identifier for r in preconds]}"
    )


def test_invariant_resolves_via_rule_not_given_step():
    import examples.bank_transfer  # noqa: F401
    from specsaver import ContractKind

    registry = get_registry()

    rule_text = "All account balances are non-negative at all times"
    derived = registry.list_by_gherkin(rule_text)
    assert len(derived) == 1
    assert derived[0].kind == ContractKind.INVARIANT
    assert "account_balance_non_negative" in derived[0].identifier


def test_rule_blocks_are_parsed():
    rules = parse_rules_file(FEATURE_PATH)
    texts = {r.text for r in rules}
    assert "All account balances are non-negative at all times" in texts
    assert "Successful transfers preserve total funds" in texts


# ---------------------------------------------------------------------------
# Scenario assembler
# ---------------------------------------------------------------------------


def test_spec_scenario_assembles_full_contract():
    import examples.bank_transfer  # noqa: F401

    scenario = SpecScenario.from_feature(FEATURE_PATH, "Transfer funds")

    assert scenario.feature == "transfer.feature"
    assert scenario.name == "Transfer funds"
    assert len(scenario.given) == 3
    assert len(scenario.then) == 5
    assert len(scenario.invariants) == 1
    assert len(scenario.then_steps) == 5
    assert len(scenario.examples) == 6


# ---------------------------------------------------------------------------
# Feature file parsing
# ---------------------------------------------------------------------------


def test_feature_file_exists():
    assert FEATURE_PATH.exists()


def test_feature_file_parses_with_official_gherkin_parser():
    scenarios = parse_feature_file(FEATURE_PATH)
    assert len(scenarios) == 10
    names = {s.name for s in scenarios}
    assert names == {"Transfer funds"}


def test_scenario_outlines_have_no_leftover_placeholders():
    scenarios = parse_feature_file(FEATURE_PATH)
    for scenario in scenarios:
        for step in scenario.steps:
            assert "<" not in step.text or ">" not in step.text


def test_examples_tables_are_structured_not_text():
    tables = parse_examples_tables_file(FEATURE_PATH)
    assert len(tables) == 6

    happy = examples_for(tables, "Transfer funds", "Happy paths")
    assert len(happy) == 2
    assert happy[0]["outcome"] == "success"


def test_every_examples_row_has_an_outcome():
    tables = parse_examples_tables_file(FEATURE_PATH)

    expected_outcome_by_table = {
        "Happy paths": "success",
        "Insufficient funds": "error:INSUFFICIENT_FUNDS",
        "Zero or negative amount": "rejected",
        "Non-existent account": "rejected",
        "Currency mismatch": "error:CURRENCY_MISMATCH",
        "Runtime fault": "error:FAULT_INJECTED",
    }

    for table in tables:
        assert "outcome" in table.columns
        expected = expected_outcome_by_table[table.table_name]
        for row in table.rows:
            assert row["outcome"] == expected


# ---------------------------------------------------------------------------
# Symmetric scenario runner
# ---------------------------------------------------------------------------

_OUTLINE = "Transfer funds"


def _all_rows() -> list[dict[str, str]]:
    tables = parse_examples_tables_file(FEATURE_PATH)
    rows: list[dict[str, str]] = []
    for t in tables:
        if t.outline_name == _OUTLINE:
            rows.extend(t.rows)
    return rows


def _row_id(row: dict[str, str]) -> str:
    return (
        f"{row['source']}->{row['target']}:{row['amount']}"
        f"{row['source_currency']}:{row['outcome']}"
    )


def test_all_examples_tables_have_pipeline_coverage():
    tables = parse_examples_tables_file(FEATURE_PATH)
    actual_tables = {t.table_name for t in tables if t.outline_name == _OUTLINE}
    covered_tables = {
        t.table_name
        for t in tables
        if t.outline_name == _OUTLINE and any(r in _all_rows() for r in t.rows)
    }
    missing = actual_tables - covered_tables
    assert not missing, f"Examples tables with no rows in _all_rows(): {missing}"


@pytest.mark.parametrize("row", _all_rows(), ids=_row_id)
def test_run_scenario_generic(row: dict[str, str]):
    """One parametrised test, symmetric flow, dispatches on row["outcome"].
    Uses the single TransferScenarioRunner exported by the domain package
    — no wiring duplicated here or in the CLI."""
    import examples.bank_transfer  # noqa: F401

    runner = examples.bank_transfer.transfer_runner
    passed, message = runner.run(row)
    assert passed, f"Scenario failed: {message}"
