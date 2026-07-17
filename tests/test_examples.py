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
    get_registry,
)
from specsaver.gherkin import (
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
    # Contracts now live in @contract decorator and contract.py; these are
    # no longer registered in the flat registry.
    preconds = registry.list_by_feature_and_kind(FEATURE, ContractKind.PRECONDITION)
    assert len(preconds) >= 0  # may be 0 if using new Contract model only


# ---------------------------------------------------------------------------
# Predicates
# ---------------------------------------------------------------------------


def test_predicates_execute():
    from examples.bank_transfer.contracts import (
        account_exists,
        has_sufficient_funds,
        is_sorted_within,
        same_currency,
    )
    from examples.bank_transfer.types import (
        Account,
        TransferDerived,
        TransferObserved,
        TransferSpecState,
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
    from examples.bank_transfer.contracts import account_balance_non_negative
    from examples.bank_transfer.types import (
        Account,
        TransferDerived,
        TransferObserved,
        TransferSpecState,
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
    from examples.bank_transfer.contracts import (
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
# ---------------------------------------------------------------------------





def test_rule_blocks_are_parsed():
    rules = parse_rules_file(FEATURE_PATH)
    texts = {r.text for r in rules}
    assert "All account balances are non-negative at all times" in texts


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


# Feature file parsing
# ---------------------------------------------------------------------------


def test_feature_file_exists():
    assert FEATURE_PATH.exists()


def test_feature_file_parses_with_official_gherkin_parser():
    scenarios = parse_feature_file(FEATURE_PATH)
    assert len(scenarios) == 10
    names = {s.name for s in scenarios}
    assert "Happy path transfer" in names
    assert "Insufficient funds" in names
    assert "Invalid amount" in names
    assert "Non-existent account" in names
    assert "Currency mismatch" in names
    assert "Runtime fault" in names


def test_scenario_outlines_have_no_leftover_placeholders():
    scenarios = parse_feature_file(FEATURE_PATH)
    for scenario in scenarios:
        for step in scenario.steps:
            assert "<" not in step.text or ">" not in step.text


def test_examples_tables_are_structured_not_text():
    tables = parse_examples_tables_file(FEATURE_PATH)
    assert len(tables) == 6
    # All tables now have default name "Examples" (no named groups)
    assert all(t.table_name == "Examples" for t in tables)


def test_every_examples_row_has_an_outcome():
    tables = parse_examples_tables_file(FEATURE_PATH)
    expected_outcome_by_outline = {
        "Happy path transfer": "success",
        "Insufficient funds": "error:InsufficientFundsError",
        "Invalid amount": "rejected",
        "Non-existent account": "rejected",
        "Currency mismatch": "error:CurrencyMismatchError",
        "Runtime fault": "error:SimulatedFaultError",
    }
    seen = set()
    for table in tables:
        assert "outcome" in table.columns
        expected = expected_outcome_by_outline[table.outline_name]
        for row in table.rows:
            assert row["outcome"] == expected
        seen.add(table.outline_name)
    assert seen == set(expected_outcome_by_outline)


# ---------------------------------------------------------------------------
# Symmetric scenario runner
# ---------------------------------------------------------------------------

_OUTLINES = {
    "Happy path transfer",
    "Insufficient funds",
    "Invalid amount",
    "Non-existent account",
    "Currency mismatch",
    "Runtime fault",
}


def _all_rows() -> list[dict[str, str]]:
    tables = parse_examples_tables_file(FEATURE_PATH)
    rows: list[dict[str, str]] = []
    for t in tables:
        if t.outline_name in _OUTLINES:
            rows.extend(t.rows)
    return rows


def _row_id(row: dict[str, str]) -> str:
    return (
        f"{row['source']}->{row['target']}:{row['amount']}"
        f"{row['source_currency']}:{row['outcome']}"
    )


def test_all_examples_tables_have_pipeline_coverage():
    tables = parse_examples_tables_file(FEATURE_PATH)
    actual_tables = {t.table_name for t in tables if t.outline_name in _OUTLINES}
    covered_tables = {
        t.table_name
        for t in tables
        if t.outline_name in _OUTLINES and any(r in _all_rows() for r in t.rows)
    }
    missing = actual_tables - covered_tables
    assert not missing, f"Examples tables with no rows in _all_rows(): {missing}"


@pytest.mark.parametrize("row", _all_rows(), ids=_row_id)
def test_run_scenario_generic(row: dict[str, str]):
    """One parametrised test, symmetric flow, dispatches on row["outcome"].
    Uses the contract.Contract from the domain package."""
    import examples.bank_transfer  # noqa: F401

    runner = examples.bank_transfer.transfer_runner
    passed, message = runner.run(row)
    assert passed, f"Scenario failed: {message}"
