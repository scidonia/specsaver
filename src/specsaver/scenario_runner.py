"""Generic scenario runner — the contract-checking flow, domain-independent.

Bundles the wiring every domain needs to execute Gherkin Examples rows
against a :class:`~specsaver.contract_model.Contract`:

  witness → materialize → context → snapshot → SpecState
  → check invariants/admissibility → execute impl → snapshot
  → check frames (generated preservation) → derived consistency
  → ensures / exception exits → invariants

The runner is parameterised by five domain-specific pieces:

  - ``contract``         — the specification (requires/ensures/exceptions/
                           invariants/derives/state_schema/writes)
  - ``materializer``     — ``materialize(witness) → context``
  - ``projection``       — ``snapshot(context) → SpecState`` (symmetric)
  - ``impl``             — ``execute(context, args)``; may define
                           ``inject_fault(name)`` for fault rows
  - ``witness_builder``  — ``row → witness``

Frame semantics: after a successful call, everything outside
``contract.writes`` must be unchanged; after an exceptional exit,
everything outside the matching ``ExcExit.writes`` (default: nothing)
must be unchanged.  Undeclared exceptions must leave the state
untouched.  Derived fields must agree with ``contract.derives``.
"""

from __future__ import annotations

from typing import Any, Protocol

from specsaver.contract_model import Contract
from specsaver.frames import check_derived, check_frame


class _Materializer(Protocol):
    def materialize(self, witness: Any) -> Any: ...


class _Projection(Protocol):
    def snapshot(self, context: Any) -> Any: ...


class _Impl(Protocol):
    def execute(self, context: Any, args: Any) -> Any: ...


class ScenarioRunner:
    """Runs Examples rows against a Contract with generated frame checks."""

    def __init__(
        self,
        contract: Contract,
        *,
        materializer: _Materializer,
        projection: _Projection,
        impl: _Impl,
        witness_builder: Any,
        cleanup: Any = None,
    ) -> None:
        self._contract = contract
        self._materializer = materializer
        self._projection = projection
        self._impl = impl
        self._witness_builder = witness_builder
        self._cleanup = cleanup

    def _run_impl(self, context, args, outcome, fault_name, before):
        if fault_name:
            inject = getattr(self._impl, "inject_fault", None)
            if inject is not None:
                inject(fault_name)
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
                    frame_violations = check_frame(
                        self._contract.state_schema, exit_.writes,
                        before, args, after,
                    )
                    if frame_violations:
                        raise RuntimeError(
                            "exception frame violated: "
                            + "; ".join(frame_violations)
                        ) from exc
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
        witness = self._witness_builder(row)
        context = self._materializer.materialize(witness)
        outcome = row.get("outcome", "")
        fault_name = row.get("fault")
        args = witness.args
        try:
            before = self._projection.snapshot(context)
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
                after = self._projection.snapshot(context)
                frame_violations = check_frame(
                    self._contract.state_schema, self._contract.writes,
                    before, args, after,
                )
                if frame_violations:
                    return False, "frame violated: " + "; ".join(frame_violations)
                derived_violations = check_derived(self._contract.derives, after)
                if derived_violations:
                    return False, "derived drift: " + "; ".join(derived_violations)
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
            after = self._projection.snapshot(context)
            if not any(
                isinstance(result, e.raises) for e in self._contract.exceptions
            ):
                # Undeclared exception (e.g. injected fault): the state
                # must be untouched.
                frame_violations = check_frame(
                    self._contract.state_schema, set(),
                    before, args, after,
                )
                if frame_violations:
                    return False, (
                        "frame violated: " + "; ".join(frame_violations)
                    )
            for inv in self._contract.invariants:
                if not inv(after):
                    return False, "invariant failed after"
            return True, "PASS"
        except Exception as exc:
            return False, str(exc)
        finally:
            if self._cleanup is not None:
                self._cleanup(context)

    def check_pre(self, row: dict[str, str]) -> tuple[bool, str]:
        witness = self._witness_builder(row)
        context = self._materializer.materialize(witness)
        try:
            before = self._projection.snapshot(context)
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
            if self._cleanup is not None:
                self._cleanup(context)
