"""Projection and refinement bridge for the bank transfer domain.

This module is the coupling layer between the concrete execution world
(SQLite database) and the abstract specification state (TransferSpecState).

It replaces the old fixtures.py with the symmetric architecture:
  - materialize(witness) → ExecutionContext  (write abstract → concrete)
  - snapshot(context) → SpecState            (read concrete → abstract)

The same snapshot is used before AND after execution (symmetry requirement).

Exports ``TransferScenarioRunner`` — the single entry point that bundles
all domain-specific wiring (witness builder, materializer, projection, impl).
Both the CLI (``--verify`` / ``--pre-only``) and pytest tests consume it.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from dataclasses import dataclass, field
from typing import Any

from examples.bank_transfer.events import EventLog, FundsReceived, TransferCompleted
from examples.bank_transfer.types import (
    Account,
    SimulatedFaultError,
    TransferArgs,
    TransferDerived,
    TransferGhost,
    TransferLimits,
    TransferObserved,
    TransferSpecState,
)

# ---------------------------------------------------------------------------
# ExecutionContext — the concrete execution world
# ---------------------------------------------------------------------------


@dataclass
class TransferExecutionContext:
    """The concrete world the implementation operates on."""

    db_path: str
    events: EventLog = field(default_factory=EventLog)
    ghost: TransferGhost = field(default_factory=TransferGhost)


# ---------------------------------------------------------------------------
# ScenarioWitness — abstract initial state + args from a Gherkin row
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TransferScenarioWitness:
    """Produced from a Gherkin Examples row by build_witness."""

    accounts: dict[str, Account]
    limits: TransferLimits | None
    args: TransferArgs
    ghost: TransferGhost = field(default_factory=TransferGhost)


# ---------------------------------------------------------------------------
# Database schema helpers
# ---------------------------------------------------------------------------


_SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    balance INTEGER NOT NULL,
    currency TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS limits (
    key TEXT PRIMARY KEY,
    value INTEGER NOT NULL
);
"""


def _populate(conn: sqlite3.Connection, accounts: dict[str, Account],
              limits: TransferLimits | None) -> None:
    conn.execute("DELETE FROM accounts")
    conn.execute("DELETE FROM limits")
    for acc in accounts.values():
        conn.execute(
            "INSERT INTO accounts (id, balance, currency) VALUES (?, ?, ?)",
            (acc.id, acc.balance, acc.currency),
        )
    if limits is not None:
        if limits.per_transfer_max is not None:
            conn.execute(
                "INSERT INTO limits (key, value) VALUES (?, ?)",
                ("per_transfer_max", limits.per_transfer_max),
            )
        if limits.daily_remaining is not None:
            conn.execute(
                "INSERT INTO limits (key, value) VALUES (?, ?)",
                ("daily_remaining", limits.daily_remaining),
            )
    conn.commit()


# ---------------------------------------------------------------------------
# Materializer — witness → ExecutionContext
# ---------------------------------------------------------------------------


class TransferMaterializer:
    """Creates a concrete ExecutionContext (temp SQLite DB) from a witness."""

    def materialize(self, witness: TransferScenarioWitness) -> TransferExecutionContext:
        fd, path = tempfile.mkstemp(suffix=".db", prefix="specsaver_")
        os.close(fd)
        with sqlite3.connect(path) as conn:
            conn.executescript(_SCHEMA)
            _populate(conn, witness.accounts, witness.limits)
        return TransferExecutionContext(
            db_path=path,
            events=EventLog(),
            ghost=witness.ghost,
        )


# ---------------------------------------------------------------------------
# Projection — ExecutionContext → immutable SpecState (symmetric)
# ---------------------------------------------------------------------------


class TransferProjection:
    """Projects the execution context into an immutable SpecState.

    Used symmetrically: before execution (pre-state) and after execution
    (post-state).  Same function, same schema, same interpretation.
    """

    def snapshot(self, context: TransferExecutionContext) -> TransferSpecState:
        with sqlite3.connect(context.db_path) as conn:
            account_rows = conn.execute(
                "SELECT id, balance, currency FROM accounts"
            ).fetchall()
            limit_rows = conn.execute(
                "SELECT key, value FROM limits"
            ).fetchall()

        accounts: dict[str, Account] = {
            row[0]: Account(id=row[0], balance=row[1], currency=row[2])
            for row in account_rows
        }

        limits: TransferLimits | None = None
        if limit_rows:
            d = dict(limit_rows)
            limits = TransferLimits(
                per_transfer_max=d.get("per_transfer_max"),
                daily_remaining=d.get("daily_remaining"),
            )

        observed = TransferObserved(
            accounts=accounts, limits=limits,
            audit_log=tuple(
                e for _, e in context.events._records
                if isinstance(e, TransferCompleted)
            ),
            notif_log=tuple(
                e for _, e in context.events._records
                if isinstance(e, FundsReceived)
            ),
        )
        derived = TransferDerived(
            total_balance=sum(a.balance for a in accounts.values())
        )

        ghost = TransferGhost(initial_total=context.ghost.initial_total)

        return TransferSpecState(
            observed=observed,
            derived=derived,
            ghost=ghost,
        )


# ---------------------------------------------------------------------------
# Witness builder — Gherkin Examples row → ScenarioWitness
# ---------------------------------------------------------------------------


def build_witness(row: dict[str, str]) -> TransferScenarioWitness:
    """Map a Gherkin Examples row to a ScenarioWitness."""
    source_id = row["source"]
    target_id = row["target"]
    amount = int(row["amount"])
    source_currency = row["source_currency"]
    target_currency = row["target_currency"]

    accounts: dict[str, Account] = {}
    accounts[source_id] = Account(
        id=source_id,
        balance=int(row["source_balance"]),
        currency=source_currency,
    )
    if row.get("target_balance"):
        accounts[target_id] = Account(
            id=target_id,
            balance=int(row["target_balance"]),
            currency=target_currency,
        )

    limits: TransferLimits | None = None
    per_transfer_limit = row.get("per_transfer_limit", "")
    if per_transfer_limit:
        limits = TransferLimits(per_transfer_max=int(per_transfer_limit))

    args = TransferArgs(source_id=source_id, target_id=target_id, amount=amount)

    return TransferScenarioWitness(
        accounts=accounts,
        limits=limits,
        args=args,
    )


# ---------------------------------------------------------------------------
# Cleanup helper
# ---------------------------------------------------------------------------


def cleanup(context: TransferExecutionContext) -> None:
    """Remove the temp database after a test."""
    if os.path.exists(context.db_path):
        os.unlink(context.db_path)


# ---------------------------------------------------------------------------
# Scenario runner — single export that bundles all domain wiring
# ---------------------------------------------------------------------------
# Both the CLI (--verify / --pre-only) and pytest tests consume this
# runner, so the wiring lives in exactly one place per domain.


class _FaultState:
    def __init__(self) -> None:
        self.pending: str | None = None

    def inject(self, fault_name: str) -> None:
        self.pending = fault_name

    def consume(self) -> str | None:
        f = self.pending
        self.pending = None
        return f


class _FaultableTransferService:
    def __init__(self, inner: Any = None) -> None:
        from examples.bank_transfer.service import TransferService

        self._inner = inner or TransferService()

    def execute(self, context, args):
        fault = _fault_state.consume()
        if fault == "simulated_fault":
            raise SimulatedFaultError(
                source_id=args.source_id,
                target_id=args.target_id,
                amount=args.amount,
                message="Simulated runtime fault",
            )
        result = self._inner.transfer(
            context.db_path, args.source_id, args.target_id, args.amount
        )
        context.events.emit(
            "audit",
            TransferCompleted(
                transaction_id=result.transaction_id,
                source_id=args.source_id,
                target_id=args.target_id,
                amount=args.amount,
            ),
        )
        context.events.emit(
            "notification",
            FundsReceived(target_id=args.target_id, amount=args.amount),
        )
        return result


_fault_state = _FaultState()


class TransferScenarioRunner:
    """Bundles the domain wiring needed to run a scenario.

    Uses the new Contract model — all predicates are in one place,
    with no dependency on SpecScenario or the registry.
    """

    def __init__(self) -> None:
        from examples.bank_transfer.contract import transfer_contract

        self._contract = transfer_contract
        self._materializer = TransferMaterializer()
        self._projection = TransferProjection()
        self._impl = _FaultableTransferService()
        self._fault_state = _fault_state

    def _run_impl(self, context, args, outcome, fault_name, before):
        if fault_name:
            self._fault_state.inject(fault_name)
        if outcome and outcome.startswith("error:"):
            expected = outcome.split(":", 1)[1]
        else:
            expected = None
        try:
            return self._impl.execute(context, args), None
        except Exception as exc:
            exc_name = type(exc).__name__
            matching = [
                e for e in self._contract.exceptions
                if isinstance(exc, e.raises)
            ]
            if matching:
                after = self._projection.snapshot(context)
                for exit_ in matching:
                    if not all(p(before, args) for p in exit_.when):
                        continue
                    for p in exit_.ensures:
                        if not p(before, args, exc, after):
                            raise RuntimeError(
                                "exception ensures violated"
                            ) from exc
                    break
                else:
                    raise RuntimeError(
                        f"exception {exc_name} has no matching when"
                    ) from exc
            if expected and exc_name != expected:
                raise
            return exc, exc_name

    def run(self, row: dict[str, str]) -> tuple[bool, str]:
        witness = build_witness(row)
        context = self._materializer.materialize(witness)
        outcome = row.get("outcome", "")
        fault_name = row.get("fault")
        args = witness.args
        try:
            projection = TransferProjection()
            before = projection.snapshot(context)
            for inv in self._contract.invariants:
                if not inv(before):
                    return False, f"invariant failed: {inv}"
            pre_passed = all(p(before, args) for p in self._contract.requires)
            if outcome == "rejected":
                if pre_passed:
                    return False, "expected rejection but admissibility held"
                return True, "REJECTED"
            if not pre_passed:
                return False, "admissibility failed"
            if outcome == "success":
                result, _ = self._run_impl(context, args, outcome, fault_name, before)
                after = projection.snapshot(context)
                for ens in self._contract.ensures:
                    if not ens(before, args, result, after):
                        return False, "postcondition failed"
                for inv in self._contract.invariants:
                    if not inv(after):
                        return False, "invariant failed after"
                return True, "PASS"
            result, code = self._run_impl(context, args, outcome, fault_name, before)
            if outcome.startswith("error:") and code != outcome.split(":", 1)[1]:
                return False, f"expected {outcome} but got code {code}"
            after = projection.snapshot(context)
            # On error paths, postconditions don't apply — exceptions handle that.
            if outcome == "success":
                for ens in self._contract.ensures:
                    if not ens(before, args, result, after):
                        return False, "postcondition failed"
            for inv in self._contract.invariants:
                if not inv(after):
                    return False, "invariant failed after"
            return True, "PASS"
        except Exception as exc:
            return False, str(exc)
        finally:
            cleanup(context)

    def check_pre(self, row: dict[str, str]) -> tuple[bool, str]:
        witness = build_witness(row)
        projection = TransferProjection()
        context = self._materializer.materialize(witness)
        try:
            before = projection.snapshot(context)
            args = witness.args
            pre_passed = all(
                p(before, args) for p in self._contract.requires
            )
            outcome = row.get("outcome", "")
            if outcome == "rejected":
                msg = "REJECTED" if not pre_passed else "FAIL: admissibility held"
                return (not pre_passed, msg)
            msg = "PASS" if pre_passed else "FAIL: admissibility failed"
            return (pre_passed, msg)
        finally:
            cleanup(context)
