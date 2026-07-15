"""Entry-point verification — run every registered contract for an operation.

This closes the loop between contracts and tests: instead of a test author
hand-listing individual precondition/postcondition calls (which silently
falls out of sync when a new contract is added), tests ask the registry
for *every* contract declared for an entry point and run all of them.

For this to work, every precondition for entry point E must share the
canonical signature `Pre(state, args) -> bool`, and every postcondition
must share `Post(old_state, args, result, new_state) -> bool` — see
`specsaver.contract` and `specsaver.args` module docstrings.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from specsaver.binding import bind_call
from specsaver.registry import ContractRecord, get_registry


@dataclass
class ContractCheck:
    identifier: str
    passed: bool
    error: str | None = None


@dataclass
class EntryPointResult:
    entry_point: str
    precondition_checks: list[ContractCheck] = field(default_factory=list)
    postcondition_checks: list[ContractCheck] = field(default_factory=list)
    invariant_checks_before: list[ContractCheck] = field(default_factory=list)
    invariant_checks_after: list[ContractCheck] = field(default_factory=list)
    result: Any = None
    skipped_call: bool = False

    @property
    def preconditions_held(self) -> bool:
        return all(c.passed for c in self.precondition_checks)

    @property
    def postconditions_held(self) -> bool:
        return all(c.passed for c in self.postcondition_checks)

    @property
    def invariants_held(self) -> bool:
        return all(
            c.passed for c in self.invariant_checks_before + self.invariant_checks_after
        )

    @property
    def ok(self) -> bool:
        return (
            self.preconditions_held
            and self.postconditions_held
            and self.invariants_held
        )

    def failures(self) -> list[ContractCheck]:
        return [
            c
            for c in (
                self.precondition_checks
                + self.postcondition_checks
                + self.invariant_checks_before
                + self.invariant_checks_after
            )
            if not c.passed
        ]

    def describe_failures(self) -> str:
        lines = []
        for c in self.failures():
            detail = f": {c.error}" if c.error else ""
            lines.append(f"{c.identifier}{detail}")
        return "; ".join(lines)


def _run_checks(records: list[ContractRecord], *call_args: Any) -> list[ContractCheck]:
    checks: list[ContractCheck] = []
    for r in records:
        try:
            passed = bool(r.func(*call_args))
            checks.append(ContractCheck(identifier=r.identifier, passed=passed))
        except Exception as e:  # noqa: BLE001 - report, don't hide, contract errors
            checks.append(
                ContractCheck(identifier=r.identifier, passed=False, error=str(e))
            )
    return checks


def check_preconditions(entry_point: str, state: Any, args: Any) -> list[ContractCheck]:
    """Run every registered precondition for entry_point against (state, args)."""
    records = get_registry().preconditions_for(entry_point)
    return _run_checks(records, state, args)


def check_postconditions(
    entry_point: str, old_state: Any, args: Any, result: Any, new_state: Any
) -> list[ContractCheck]:
    """Run every registered postcondition for entry_point against
    (old_state, args, result, new_state)."""
    records = get_registry().postconditions_for(entry_point)
    return _run_checks(records, old_state, args, result, new_state)


def check_invariants(entry_point: str, state: Any) -> list[ContractCheck]:
    """Run every registered invariant for entry_point against (state,)."""
    records = get_registry().invariants_for(entry_point)
    return _run_checks(records, state)


def run_entry_point(
    entry_point: str,
    impl: Callable[..., Any],
    state: Any,
    args: Any,
    *,
    snapshot: Callable[[Any], Any] = copy.deepcopy,
    spread: bool = False,
    varargs_field: str | None = None,
    varkwargs_field: str | None = None,
) -> EntryPointResult:
    """Run *every* declared contract for an entry point around a call to impl.

    Order of operations:
      1. Snapshot invariants on the pre-state.
      2. Run every registered precondition.  If any fails, `impl` is NOT
         called (this mirrors Hoare-triple semantics: Pre must hold before
         the operation may execute) and the result carries only the
         precondition/invariant checks.
      3. Take an explicit snapshot of `state` (default: deepcopy) *before*
         calling impl — this becomes old_state.  `impl` is then called and
         may mutate `state` in place; the snapshot guarantees old_state
         still reflects pre-call values when postconditions run.
      4. Call impl using `args` — see `specsaver.binding.bind_call` for the
         `spread`/`varargs_field`/`varkwargs_field` parameters, which let
         `impl` have an arbitrary native Python signature (positional-only,
         *args, keyword-only, **kwargs, and default values) instead of
         requiring it to take the whole Args object as one parameter.
      5. Run every registered postcondition against (old_state, args,
         result, state_after).
      6. Re-check invariants on the post-state.

    Every check that is currently registered for the entry point runs —
    nothing needs to be hand-listed by the caller.
    """
    registry = get_registry()

    inv_before = _run_checks(registry.invariants_for(entry_point), state)
    pre_checks = check_preconditions(entry_point, state, args)

    out = EntryPointResult(
        entry_point=entry_point,
        precondition_checks=pre_checks,
        invariant_checks_before=inv_before,
    )

    if not all(c.passed for c in pre_checks):
        out.skipped_call = True
        return out

    old_state = snapshot(state)
    result = bind_call(
        impl,
        state,
        args=args,
        spread=spread,
        varargs_field=varargs_field,
        varkwargs_field=varkwargs_field,
    )
    out.result = result

    out.postcondition_checks = check_postconditions(
        entry_point, old_state, args, result, state
    )
    out.invariant_checks_after = _run_checks(
        registry.invariants_for(entry_point), state
    )

    return out
