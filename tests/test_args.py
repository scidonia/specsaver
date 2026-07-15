"""Tests for the canonical Args/Result base classes and their enforcement
at contract-registration time (see specsaver.args, specsaver.contract)."""

from dataclasses import FrozenInstanceError, dataclass

import pytest

from specsaver import Args, Result, get_registry, postcondition, precondition


def test_args_is_frozen():
    @dataclass(frozen=True)
    class MyArgs(Args):
        x: int

    a = MyArgs(x=1)
    with pytest.raises(FrozenInstanceError):
        a.x = 2  # type: ignore[misc]


def test_result_is_frozen():
    @dataclass(frozen=True)
    class MyResult(Result):
        ok: bool

    r = MyResult(ok=True)
    with pytest.raises(FrozenInstanceError):
        r.ok = False  # type: ignore[misc]


def test_precondition_requires_args_subtype_when_entry_point_set():
    """A precondition tagged with entry_point must annotate its second
    parameter with an Args subclass — a plain type is rejected."""

    with pytest.raises(TypeError, match="Args subclass"):

        @precondition(entry_point="ep_plain_type")
        def bad_pre(state: object, args: int) -> bool:
            return args > 0


def test_precondition_missing_annotation_is_rejected():

    with pytest.raises(TypeError, match="type-annotated"):

        @precondition(entry_point="ep_missing_annotation")
        def bad_pre(state, args) -> bool:
            return True


def test_entry_point_enforces_single_canonical_args_type():
    """Two preconditions on the same entry_point must agree on the Args type."""

    @dataclass(frozen=True)
    class FooArgs(Args):
        x: int

    @precondition(entry_point="ep_consistency")
    def foo_pre_first(state: object, args: FooArgs) -> bool:
        return args.x > 0

    @dataclass(frozen=True)
    class BarArgs(Args):
        y: int

    with pytest.raises(ValueError, match="already uses"):

        @precondition(entry_point="ep_consistency")
        def foo_pre_second(state: object, args: BarArgs) -> bool:
            return args.y > 0


def test_entry_point_enforces_single_canonical_result_type():
    """Two postconditions on the same entry_point must agree on the Result type."""

    @dataclass(frozen=True)
    class OpArgs(Args):
        x: int

    @dataclass(frozen=True)
    class OkResult(Result):
        ok: bool

    @postcondition(entry_point="ep_result_consistency")
    def op_post_first(old_s, args: OpArgs, result: OkResult, new_s) -> bool:
        return result.ok

    @dataclass(frozen=True)
    class OtherResult(Result):
        value: int

    with pytest.raises(ValueError, match="already uses"):

        @postcondition(entry_point="ep_result_consistency")
        def op_post_second(old_s, args: OpArgs, result: OtherResult, new_s) -> bool:
            return result.value > 0


def test_registry_exposes_args_and_result_types():

    @dataclass(frozen=True)
    class OpArgs(Args):
        x: int

    @dataclass(frozen=True)
    class OpResult(Result):
        ok: bool

    @precondition(entry_point="ep_lookup")
    def op_pre(state: object, args: OpArgs) -> bool:
        return args.x > 0

    @postcondition(entry_point="ep_lookup")
    def op_post(old_s, args: OpArgs, result: OpResult, new_s) -> bool:
        return result.ok

    registry = get_registry()
    assert registry.args_type_for("ep_lookup") is OpArgs
    assert registry.result_type_for("ep_lookup") is OpResult
    assert registry.args_type_for("nonexistent") is None


def test_contracts_without_entry_point_are_unconstrained():
    """Contracts that don't declare entry_point are not subject to the
    Args/Result signature check — arbitrary pure predicates remain free-form."""

    @precondition
    def free_form_pre(state: object, x: int) -> bool:
        return x > 0

    assert free_form_pre(None, 5) is True
