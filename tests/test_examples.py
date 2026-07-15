"""Integration tests for the bank transfer example.

Key principle exercised throughout this file: tests must not hand-list
individual precondition/postcondition function names.  They query the
registry for entry_point="transfer" (directly, or via run_entry_point) so
that adding/removing a contract in contracts.py is automatically reflected
here — the only thing that can go stale is the *shape* sanity check
(`test_transfer_entry_point_contract_shape`), which exists precisely to
force a conscious acknowledgement when the contract set changes.
"""

from pathlib import Path

import pytest

from specsaver import check_postconditions, check_preconditions, run_entry_point
from specsaver.gherkin import (
    examples_for,
    parse_examples_tables_file,
    parse_feature_file,
)

FEATURE_PATH = (
    Path(__file__).parent.parent / "examples" / "bank_transfer" / "transfer.feature"
)


def test_bank_transfer_example_loads():
    """Verify the bank transfer example module imports without errors."""
    import examples.bank_transfer  # noqa: F401


def test_all_contracts_registered():
    """Verify all contracts from the example are in the registry."""
    import examples.bank_transfer  # noqa: F401
    from specsaver import ContractKind, get_registry

    registry = get_registry()

    preconds = registry.list_by_kind(ContractKind.PRECONDITION)
    assert len(preconds) >= 4, f"Expected >= 4 preconditions, got {len(preconds)}"

    postconds = registry.list_by_kind(ContractKind.POSTCONDITION)
    assert len(postconds) >= 4, f"Expected >= 4 postconditions, got {len(postconds)}"


def test_predicates_execute():
    """Verify the reusable predicates produce correct results."""
    from examples.bank_transfer import (
        Account,
        AccountState,
        account_exists,
        has_sufficient_funds,
        is_sorted_within,
        same_currency,
    )

    state = AccountState(
        accounts={
            "a1": Account(id="a1", balance=100, currency="USD"),
            "a2": Account(id="a2", balance=50, currency="USD"),
        }
    )

    assert account_exists(state, "a1")
    assert not account_exists(state, "a3")
    assert has_sufficient_funds(state, "a1", 50)
    assert not has_sufficient_funds(state, "a1", 200)
    assert same_currency(state, "a1", "a2")

    # Structural recursion test
    assert is_sorted_within([1, 2, 3, 4], 0, 3)
    assert not is_sorted_within([1, 3, 2, 4], 0, 3)


# ---------------------------------------------------------------------------
# Entry-point contract discovery
#
# _EXPECTED_TRANSFER_* declare the authoritative shape of the "transfer"
# entry point's contract set.  test_transfer_entry_point_contract_shape is
# a sanity check: if a contract is silently added/removed, it fails and
# forces a conscious update.  Everything below this section (the pipeline
# tests) does NOT hand-list contract names — it queries the registry via
# run_entry_point, so a newly *added* contract is automatically exercised
# without touching test code.
# ---------------------------------------------------------------------------

_EXPECTED_TRANSFER_PRECONDITIONS = {
    "examples.bank_transfer.contracts.precondition.transfer_pre_valid_amount",
    "examples.bank_transfer.contracts.precondition.transfer_pre_accounts_exist",
    "examples.bank_transfer.contracts.precondition.transfer_pre_sufficient_funds",
    "examples.bank_transfer.contracts.precondition.transfer_pre_same_currency",
}

_EXPECTED_TRANSFER_POSTCONDITIONS = {
    "examples.bank_transfer.contracts.postcondition.transfer_post_total_preserved",
    "examples.bank_transfer.contracts.postcondition.transfer_post_source_decreased",
    "examples.bank_transfer.contracts.postcondition.transfer_post_target_increased",
    "examples.bank_transfer.contracts.postcondition."
    "transfer_post_all_balances_non_negative",
}

_EXPECTED_TRANSFER_INVARIANTS = {
    "examples.bank_transfer.contracts.invariant.account_balance_non_negative",
}


def test_transfer_entry_point_contract_shape():
    """The registry's view of entry_point='transfer' matches expectations.

    This is the enforcement point: it is the *only* place a contract name
    is hand-listed.  Every other test discovers contracts through the
    registry, so this single check is what forces acknowledgement when the
    contract set for 'transfer' changes.
    """
    import examples.bank_transfer  # noqa: F401
    from specsaver import get_registry

    registry = get_registry()
    pre_ids = {r.identifier for r in registry.preconditions_for("transfer")}
    post_ids = {r.identifier for r in registry.postconditions_for("transfer")}
    inv_ids = {r.identifier for r in registry.invariants_for("transfer")}

    assert pre_ids == _EXPECTED_TRANSFER_PRECONDITIONS
    assert post_ids == _EXPECTED_TRANSFER_POSTCONDITIONS
    assert inv_ids == _EXPECTED_TRANSFER_INVARIANTS


def test_check_preconditions_and_postconditions_directly():
    """Exercise the check_preconditions/check_postconditions API surface."""
    import examples.bank_transfer  # noqa: F401
    from examples.bank_transfer.contracts import (
        Account,
        AccountState,
        TransferArgs,
        TransferReceipt,
    )

    old_state = AccountState(
        accounts={
            "a1": Account(id="a1", balance=100, currency="USD"),
            "a2": Account(id="a2", balance=50, currency="USD"),
        }
    )
    args = TransferArgs(source_id="a1", target_id="a2", amount=30)

    pre_checks = check_preconditions("transfer", old_state, args)
    assert {c.identifier for c in pre_checks} == _EXPECTED_TRANSFER_PRECONDITIONS
    assert all(c.passed for c in pre_checks), [c for c in pre_checks if not c.passed]

    new_state = AccountState(
        accounts={
            "a1": Account(id="a1", balance=70, currency="USD"),
            "a2": Account(id="a2", balance=80, currency="USD"),
        }
    )
    result = TransferReceipt("tx1", "a1", "a2", 30, True)

    post_checks = check_postconditions("transfer", old_state, args, result, new_state)
    assert {c.identifier for c in post_checks} == _EXPECTED_TRANSFER_POSTCONDITIONS
    assert all(c.passed for c in post_checks), [c for c in post_checks if not c.passed]


def test_transfer_post_total_preserved_detects_violation():
    """Verify the postcondition catches a conservation violation."""
    from examples.bank_transfer.contracts import (
        Account,
        AccountState,
        TransferArgs,
        TransferReceipt,
        transfer_post_total_preserved,
    )

    old_s = AccountState(
        accounts={
            "a1": Account(id="a1", balance=100, currency="USD"),
            "a2": Account(id="a2", balance=50, currency="USD"),
        }
    )
    # mistakenly increased total by 100
    new_s = AccountState(
        accounts={
            "a1": Account(id="a1", balance=150, currency="USD"),
            "a2": Account(id="a2", balance=100, currency="USD"),
        }
    )
    args = TransferArgs(source_id="a1", target_id="a2", amount=30)
    result = TransferReceipt("tx1", "a1", "a2", 30, True)
    assert not transfer_post_total_preserved(old_s, args, result, new_s)


def test_frame_and_effect():
    """Verify frame and effect declarations produce correct objects."""
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
    assert Field("ghost.daily_remaining") in reads.reads

    eff = transfer_effect()
    assert "database" in eff.uses
    assert any(e.name == "audit.transfer_completed" for e in eff.emits)


def test_invariant():
    """Verify invariants evaluate correctly."""
    from examples.bank_transfer import (
        Account,
        AccountState,
        account_balance_non_negative,
    )

    good = AccountState(
        accounts={
            "a1": Account(id="a1", balance=100, currency="USD"),
            "a2": Account(id="a2", balance=0, currency="USD"),
        }
    )
    assert account_balance_non_negative(good)

    bad = AccountState(
        accounts={
            "a1": Account(id="a1", balance=-5, currency="USD"),
        }
    )
    assert not account_balance_non_negative(bad)


# ---------------------------------------------------------------------------
# Gherkin → Contract traceability
# ---------------------------------------------------------------------------


def test_contracts_carry_gherkin_origin():
    """Every contract knows which Gherkin step it flows from."""
    import examples.bank_transfer  # noqa: F401
    from specsaver import get_registry

    registry = get_registry()

    total_step = "the total balance across all accounts is unchanged"
    derived = registry.list_by_gherkin(total_step)
    assert len(derived) >= 1, f"No contracts for: {total_step}"
    assert any("transfer_post_total_preserved" in r.identifier for r in derived), (
        f"Expected transfer_post_total_preserved, "
        f"got: {[r.identifier for r in derived]}"
    )


def test_contracts_declare_feature_file():
    """Contracts declare which feature file they belong to."""
    import examples.bank_transfer  # noqa: F401
    from specsaver import get_registry

    registry = get_registry()
    records = registry.list_by_module("examples.bank_transfer.contracts")

    with_feature = [r for r in records if r.feature == "transfer.feature"]
    assert len(with_feature) >= 10, (
        f"Expected >=10 contracts with feature set, got {len(with_feature)}"
    )


def test_gherkin_step_resolves_to_contracts():
    """Given a Gherkin step, find its semantic propositions."""
    import examples.bank_transfer  # noqa: F401
    from specsaver import get_registry

    registry = get_registry()

    # 'an account "<source>" with balance <source_balance> in currency
    # "<currency>" resolves to 4 preconditions + 1 invariant
    given_step = (
        'an account "<source>" with balance <source_balance> in currency "<currency>"'
    )
    derived = registry.list_by_gherkin(given_step)
    assert len(derived) >= 4, (
        f"'{given_step}' should resolve to >=4 contracts, got {len(derived)}: "
        f"{[r.identifier for r in derived]}"
    )


def test_feature_file_exists():
    """The feature file referenced by contracts actually exists."""
    assert FEATURE_PATH.exists(), f"Feature file not found: {FEATURE_PATH}"


def test_feature_file_parses_with_official_gherkin_parser():
    """The feature file is valid Gherkin, parsed by the official Cucumber parser."""
    scenarios = parse_feature_file(FEATURE_PATH)
    assert len(scenarios) == 8, f"Expected 8 concrete scenarios, got {len(scenarios)}"

    names = {s.name for s in scenarios}
    assert "Transfer between two accounts" in names
    assert "Transfer is rejected when preconditions fail" in names
    assert "Transfer to non-existent account is rejected" in names


def test_scenario_outlines_have_no_leftover_placeholders():
    """Every <placeholder> must be substituted by the Examples table."""
    scenarios = parse_feature_file(FEATURE_PATH)
    for scenario in scenarios:
        for step in scenario.steps:
            assert "<" not in step.text or ">" not in step.text, (
                f"Unresolved placeholder in {scenario.name!r}: {step.text!r}"
            )


def test_examples_tables_are_structured_not_text():
    """Concrete test data comes from structured Examples rows, not step text."""
    tables = parse_examples_tables_file(FEATURE_PATH)
    assert len(tables) == 4

    happy = examples_for(tables, "Transfer between two accounts", "Happy paths")
    assert len(happy) == 3
    assert happy[0] == {
        "source": "A1",
        "target": "A2",
        "source_balance": "100",
        "target_balance": "50",
        "amount": "30",
        "currency": "USD",
    }


# ---------------------------------------------------------------------------
# Full pipeline: Gherkin Examples → Contracts → Implementation
#
# Concrete values are read directly from the .feature file's Examples
# tables — nothing is hardcoded in Python.  Every pipeline test below runs
# ALL registered preconditions/postconditions for entry_point="transfer"
# via run_entry_point, rather than hand-listing individual contract calls.
#
# _COVERED_TABLES declares every (outline, table) pair that has a
# corresponding pipeline test below.  test_all_examples_tables_have_coverage
# fails if the feature file ever gains a table that isn't in this set —
# that is a specification-sanity check: no Examples table may go untested.
# ---------------------------------------------------------------------------

_COVERED_TABLES: set[tuple[str, str]] = {
    ("Transfer between two accounts", "Happy paths"),
    ("Transfer is rejected when preconditions fail", "Insufficient funds"),
    ("Transfer is rejected when preconditions fail", "Zero or negative amount"),
    ("Transfer to non-existent account is rejected", "Non-existent account"),
}


def _rows_for(outline_name: str, table_name: str) -> list[dict[str, str]]:
    tables = parse_examples_tables_file(FEATURE_PATH)
    return examples_for(tables, outline_name, table_name)


def _happy_path_rows() -> list[dict[str, str]]:
    return _rows_for("Transfer between two accounts", "Happy paths")


def _rejected_rows(table_name: str) -> list[dict[str, str]]:
    return _rows_for("Transfer is rejected when preconditions fail", table_name)


def _nonexistent_account_rows() -> list[dict[str, str]]:
    return _rows_for(
        "Transfer to non-existent account is rejected", "Non-existent account"
    )


def _row_id(row: dict[str, str]) -> str:
    return f"{row['source']}->{row['target']}:{row['amount']}{row['currency']}"


def test_all_examples_tables_have_pipeline_coverage():
    """Every Examples table in the feature file has a corresponding test.

    This is a specification-sanity check (see docs: 'Specification
    Testing'): if a new Scenario Outline or Examples table is added to
    transfer.feature without wiring a pipeline test for it, this fails
    loudly instead of silently leaving part of the spec unverified.
    """
    tables = parse_examples_tables_file(FEATURE_PATH)
    actual = {(t.outline_name, t.table_name) for t in tables}
    missing = actual - _COVERED_TABLES
    stale = _COVERED_TABLES - actual
    assert not missing, f"Examples tables with no pipeline test: {missing}"
    assert not stale, (
        f"_COVERED_TABLES references tables no longer in the feature: {stale}"
    )


@pytest.mark.parametrize("row", _happy_path_rows(), ids=_row_id)
def test_full_pipeline_happy_path(row: dict[str, str]):
    """Every 'Happy paths' Examples row satisfies every registered
    pre/postcondition for entry_point='transfer' against the impl."""
    from examples.bank_transfer.contracts import (
        TRANSFER,
        Account,
        AccountState,
        TransferArgs,
    )
    from examples.bank_transfer.service import TransferService

    source, target = row["source"], row["target"]
    source_balance = int(row["source_balance"])
    target_balance = int(row["target_balance"])
    amount = int(row["amount"])
    currency = row["currency"]

    state = AccountState(
        accounts={
            source: Account(id=source, balance=source_balance, currency=currency),
            target: Account(id=target, balance=target_balance, currency=currency),
        }
    )
    args = TransferArgs(source_id=source, target_id=target, amount=amount)

    outcome = run_entry_point(TRANSFER, TransferService().transfer, state, args)

    assert outcome.preconditions_held, outcome.describe_failures()
    assert not outcome.skipped_call
    assert outcome.result.success
    assert outcome.postconditions_held, outcome.describe_failures()
    assert outcome.invariants_held, outcome.describe_failures()
    assert state.accounts[source].balance == source_balance - amount
    assert state.accounts[target].balance == target_balance + amount


@pytest.mark.parametrize("row", _rejected_rows("Insufficient funds"), ids=_row_id)
def test_full_pipeline_insufficient_funds(row: dict[str, str]):
    """Every 'Insufficient funds' Examples row is rejected before the
    implementation is ever called."""
    from examples.bank_transfer.contracts import (
        TRANSFER,
        Account,
        AccountState,
        TransferArgs,
    )
    from examples.bank_transfer.service import TransferService

    source, target = row["source"], row["target"]
    source_balance = int(row["source_balance"])
    target_balance = int(row["target_balance"])
    amount = int(row["amount"])
    currency = row["currency"]

    state = AccountState(
        accounts={
            source: Account(id=source, balance=source_balance, currency=currency),
            target: Account(id=target, balance=target_balance, currency=currency),
        }
    )
    args = TransferArgs(source_id=source, target_id=target, amount=amount)

    outcome = run_entry_point(TRANSFER, TransferService().transfer, state, args)

    assert not outcome.preconditions_held
    assert outcome.skipped_call, "implementation must not run when a precondition fails"
    assert state.accounts[source].balance == source_balance
    assert state.accounts[target].balance == target_balance


@pytest.mark.parametrize("row", _rejected_rows("Zero or negative amount"), ids=_row_id)
def test_full_pipeline_invalid_amount(row: dict[str, str]):
    """Every 'Zero or negative amount' Examples row is rejected."""
    from examples.bank_transfer.contracts import (
        TRANSFER,
        Account,
        AccountState,
        TransferArgs,
    )
    from examples.bank_transfer.service import TransferService

    source, target = row["source"], row["target"]
    amount = int(row["amount"])
    currency = row["currency"]

    state = AccountState(
        accounts={
            source: Account(
                id=source, balance=int(row["source_balance"]), currency=currency
            ),
            target: Account(
                id=target, balance=int(row["target_balance"]), currency=currency
            ),
        }
    )
    args = TransferArgs(source_id=source, target_id=target, amount=amount)

    outcome = run_entry_point(TRANSFER, TransferService().transfer, state, args)

    assert not outcome.preconditions_held
    assert outcome.skipped_call


@pytest.mark.parametrize("row", _nonexistent_account_rows(), ids=_row_id)
def test_full_pipeline_nonexistent_account_rejected(row: dict[str, str]):
    """Every 'Non-existent account' Examples row is rejected.

    Covers Scenario Outline: Transfer to non-existent account is rejected.
    """
    from examples.bank_transfer.contracts import (
        TRANSFER,
        Account,
        AccountState,
        TransferArgs,
    )
    from examples.bank_transfer.service import TransferService

    source, target = row["source"], row["target"]
    amount = int(row["amount"])
    currency = row["currency"]

    # The target account is intentionally absent — "Given an account
    # <target> does not exist".
    state = AccountState(
        accounts={
            source: Account(
                id=source, balance=int(row["source_balance"]), currency=currency
            ),
        }
    )
    args = TransferArgs(source_id=source, target_id=target, amount=amount)

    outcome = run_entry_point(TRANSFER, TransferService().transfer, state, args)

    assert not outcome.preconditions_held
    assert outcome.skipped_call
