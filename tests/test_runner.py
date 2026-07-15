"""Unit tests for specsaver.runner — the symmetric scenario runner.

These use synthetic witnesses, materializers, projections, and impls
to test the runner's dispatch logic in isolation from any real domain.
"""

from dataclasses import dataclass, field

import pytest

from specsaver.registry import ContractRecord
from specsaver.runner import ScenarioAssertionError, run_scenario
from specsaver.scenario import SpecScenario
from specsaver.types import ContractKind

# ---------------------------------------------------------------------------
# Synthetic domain types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Args:
    amount: int


@dataclass(frozen=True)
class _Result:
    code: str | None = None


@dataclass(frozen=True)
class _Witness:
    args: _Args
    amount: int


@dataclass
class _Context:
    """Minimal execution context — just a mutable dict."""
    data: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Synthetic materializer / projection / impl
# ---------------------------------------------------------------------------


class _Materializer:
    def materialize(self, witness: _Witness) -> _Context:
        return _Context(data={"amount": witness.amount})


class _Projection:
    """Identity projection — snapshot returns the context's data as-is."""

    def snapshot(self, context: _Context) -> dict:
        return dict(context.data)


def _record(identifier: str, kind: ContractKind, func) -> ContractRecord:
    return ContractRecord(
        identifier=identifier,
        kind=kind,
        func=func,
        module="test_runner",
        qualname=identifier,
    )


def _amount_positive(state: dict, args: _Args) -> bool:
    return args.amount > 0


def _amount_unchanged(old: dict, args: _Args, result: _Result, new: dict) -> bool:
    return new.get("amount") == old.get("amount")


def _always_true(state: dict) -> bool:
    return True


def _always_false(state: dict) -> bool:
    return False


def _make_scenario(then=(), invariants=(), exceptionals=()) -> SpecScenario:
    given = (
        _record("pre.amount_positive", ContractKind.PRECONDITION, _amount_positive),
    )
    return SpecScenario(
        feature="test.feature",
        name="test",
        given=given,
        given_steps=("a positive amount",),
        when_text="an action",
        then=then,
        then_steps=("a result",),
        invariants=invariants,
        exceptionals=exceptionals,
        examples=(),
    )


_MAT = _Materializer()
_PROJ = _Projection()


# ---------------------------------------------------------------------------
# outcome="success"
# ---------------------------------------------------------------------------


def test_success_without_impl_only_checks_admissibility():
    scenario = _make_scenario()
    witness = _Witness(args=_Args(5), amount=5)

    result = run_scenario(
        scenario, witness, materializer=_MAT, projection=_PROJ, outcome="success"
    )

    assert result.admissibility_held
    assert result.skipped_call is True


def test_success_but_admissibility_fails_raises():
    scenario = _make_scenario()
    witness = _Witness(args=_Args(-5), amount=-5)

    with pytest.raises(ScenarioAssertionError, match="admissibility"):
        run_scenario(
            scenario, witness, materializer=_MAT, projection=_PROJ, outcome="success"
        )


def test_success_with_impl_checks_transitions_and_invariants():
    then = (
        _record(
            "post.amount_unchanged", ContractKind.POSTCONDITION, _amount_unchanged
        ),
    )
    invariants = (
        _record("inv.always_true", ContractKind.INVARIANT, _always_true),
    )
    scenario = _make_scenario(then=then, invariants=invariants)
    witness = _Witness(args=_Args(5), amount=5)

    class _Impl:
        def execute(self, context, args):
            return _Result(code=None)

    result = run_scenario(
        scenario, witness, materializer=_MAT, projection=_PROJ,
        impl=_Impl(), outcome="success",
    )

    assert result.transitions_held
    assert result.invariants_held
    assert result.skipped_call is False


def test_success_with_impl_transition_failure_raises():
    then = (
        _record(
            "post.amount_unchanged", ContractKind.POSTCONDITION, _amount_unchanged
        ),
    )
    scenario = _make_scenario(then=then)
    witness = _Witness(args=_Args(5), amount=5)

    class _Impl:
        def execute(self, context, args):
            # Corrupt the state so the postcondition fails.
            context.data["amount"] = 999
            return _Result(code=None)

    with pytest.raises(ScenarioAssertionError, match="transitions/invariants"):
        run_scenario(
            scenario, witness, materializer=_MAT, projection=_PROJ,
            impl=_Impl(), outcome="success",
        )


# ---------------------------------------------------------------------------
# outcome="rejected"
# ---------------------------------------------------------------------------


def test_rejected_admissibility_failure_is_expected():
    scenario = _make_scenario()
    witness = _Witness(args=_Args(-5), amount=-5)

    result = run_scenario(
        scenario, witness, materializer=_MAT, projection=_PROJ, outcome="rejected"
    )

    assert not result.admissibility_held
    assert result.skipped_call is True


def test_rejected_but_admissibility_holds_raises():
    scenario = _make_scenario()
    witness = _Witness(args=_Args(5), amount=5)

    with pytest.raises(ScenarioAssertionError, match="admissibility checks passed"):
        run_scenario(
            scenario, witness, materializer=_MAT, projection=_PROJ, outcome="rejected"
        )


def test_rejected_never_calls_impl():
    scenario = _make_scenario()
    witness = _Witness(args=_Args(-5), amount=-5)

    class _PoisonPill:
        def execute(self, context, args):
            raise RuntimeError("impl should never be called for a rejected row")

    result = run_scenario(
        scenario, witness, materializer=_MAT, projection=_PROJ,
        impl=_PoisonPill(), outcome="rejected",
    )
    assert result.skipped_call is True


# ---------------------------------------------------------------------------
# outcome="error:CODE"
# ---------------------------------------------------------------------------


def test_error_outcome_matches_expected_code():
    scenario = _make_scenario()
    witness = _Witness(args=_Args(5), amount=5)

    class _Impl:
        def execute(self, context, args):
            return _Result(code="FAULT_INJECTED")

    result = run_scenario(
        scenario, witness, materializer=_MAT, projection=_PROJ,
        impl=_Impl(), outcome="error:FAULT_INJECTED",
    )
    assert result.result.code == "FAULT_INJECTED"


def test_error_outcome_code_mismatch_raises():
    scenario = _make_scenario()
    witness = _Witness(args=_Args(5), amount=5)

    class _Impl:
        def execute(self, context, args):
            return _Result(code="SOMETHING_ELSE")

    with pytest.raises(ScenarioAssertionError, match="expected error code"):
        run_scenario(
            scenario, witness, materializer=_MAT, projection=_PROJ,
            impl=_Impl(), outcome="error:FAULT_INJECTED",
        )


def test_error_outcome_admissibility_failure_raises():
    scenario = _make_scenario()
    witness = _Witness(args=_Args(-5), amount=-5)

    class _Impl:
        def execute(self, context, args):
            return _Result(code="FAULT_INJECTED")

    with pytest.raises(ScenarioAssertionError, match="admissibility"):
        run_scenario(
            scenario, witness, materializer=_MAT, projection=_PROJ,
            impl=_Impl(), outcome="error:FAULT_INJECTED",
        )


# ---------------------------------------------------------------------------
# Fault injection
# ---------------------------------------------------------------------------


class _FakeFaultInjector:
    def __init__(self):
        self.injected = []

    def inject(self, fault_name: str) -> None:
        self.injected.append(fault_name)


def test_fault_injection_called_before_impl():
    scenario = _make_scenario()
    witness = _Witness(args=_Args(5), amount=5)
    fi = _FakeFaultInjector()

    class _Impl:
        def execute(self, context, args):
            return _Result(code="FAULT_INJECTED")

    run_scenario(
        scenario, witness, materializer=_MAT, projection=_PROJ,
        impl=_Impl(), fault_injector=fi, fault_name="db_locked",
        outcome="error:FAULT_INJECTED",
    )

    assert fi.injected == ["db_locked"]


# ---------------------------------------------------------------------------
# Inferred outcome (None)
# ---------------------------------------------------------------------------


def test_inferred_rejected_when_admissibility_fails():
    scenario = _make_scenario()
    witness = _Witness(args=_Args(-5), amount=-5)

    result = run_scenario(
        scenario, witness, materializer=_MAT, projection=_PROJ, outcome=None
    )
    assert result.skipped_call is True
