"""Tests for specsaver.render — math/logical rendering of contracts."""

from dataclasses import dataclass

import pytest

from specsaver import (
    Args,
    Result,
    get_registry,
    invariant,
    postcondition,
    precondition,
    render_all,
    render_contract,
    render_invariant,
    render_postcondition,
    render_precondition,
)


@pytest.fixture(autouse=True)
def _clear_registry():
    get_registry().clear()


def test_empty_entry_point_returns_true():
    assert render_precondition("no_such_ep") == "True"
    assert render_postcondition("no_such_ep") == "True"


def test_single_precondition_python():
    @dataclass(frozen=True)
    class AddArgs(Args):
        x: int

    @precondition(entry_point="add")
    def add_pre_positive(state: object, args: AddArgs) -> bool:
        return args.x > 0

    result = render_precondition("add")
    assert "args.x > 0" in result


def test_multiple_preconditions_conjoined_python():
    @dataclass(frozen=True)
    class AddArgs(Args):
        x: int

    @precondition(entry_point="add2")
    def add2_pre_positive(state: object, args: AddArgs) -> bool:
        return args.x > 0

    @precondition(entry_point="add2")
    def add2_pre_lt_100(state: object, args: AddArgs) -> bool:
        return args.x < 100

    result = render_precondition("add2")
    assert "args.x > 0 and args.x < 100" in result or "args.x > 0" in result
    # Both must appear
    assert "args.x > 0" in result
    assert "args.x < 100" in result


def test_single_precondition_math():
    @dataclass(frozen=True)
    class AddArgs(Args):
        x: int

    @precondition(entry_point="add_math")
    def add_math_pre(state: object, args: AddArgs) -> bool:
        return args.x > 0

    result = render_precondition("add_math", mode="math")
    assert result == "args.x > 0"


def test_conjunction_uses_math_symbol():
    @dataclass(frozen=True)
    class AddArgs(Args):
        x: int

    @precondition(entry_point="math_conj")
    def math_conj_a(state: object, args: AddArgs) -> bool:
        return args.x > 0

    @precondition(entry_point="math_conj")
    def math_conj_b(state: object, args: AddArgs) -> bool:
        return args.x < 100

    result = render_precondition("math_conj", mode="math")
    assert "∧" in result
    assert "args.x > 0" in result
    assert "args.x < 100" in result


def test_math_unicode_operators():
    @dataclass(frozen=True)
    class CmpArgs(Args):
        x: int

    @precondition(entry_point="cmp")
    def cmp_pre(state: object, args: CmpArgs) -> bool:
        return args.x >= 0 and args.x <= 10 and args.x != 5

    result = render_precondition("cmp", mode="math")
    assert "≥" in result
    assert "≤" in result
    assert "≠" in result
    assert "∧" in result


def test_math_quantifiers():
    @dataclass(frozen=True)
    class QArgs(Args):
        xs: list

    @dataclass
    class QState:
        values: list

    @precondition(entry_point="q")
    def q_pre(state: QState, args: QArgs) -> bool:
        from specsaver import forall

        return forall(args.xs, lambda x: x > 0)

    result = render_precondition("q", mode="math")
    assert "∀" in result
    assert "∈" in result
    assert "x > 0" in result


def test_postcondition_math():
    @dataclass(frozen=True)
    class SubArgs(Args):
        x: int

    @dataclass(frozen=True)
    class SubResult(Result):
        ok: bool

    @postcondition(entry_point="sub")
    def sub_post(old_s, args: SubArgs, result: SubResult, new_s) -> bool:
        return result.ok

    result = render_postcondition("sub", mode="math")
    assert "result.ok" in result


def test_invariant_math():
    @dataclass
    class IVState:
        value: int

    @invariant(entry_point="inv_test")
    def inv_test(state: IVState) -> bool:
        return state.value >= 0

    result = render_invariant("inv_test", mode="math")
    assert "≥" in result
    assert "state.value" in result


def test_render_contract_structure():
    @dataclass(frozen=True)
    class SimpleArgs(Args):
        x: int

    @precondition(entry_point="struct")
    def struct_pre(state: object, args: SimpleArgs) -> bool:
        return args.x > 0

    result = render_contract("struct")
    assert "pre:" in result
    assert "post:" in result
    # No invariants means no invariant line
    assert "invariant" not in result


def test_render_all_multiple_entry_points():
    @dataclass(frozen=True)
    class AArgs(Args):
        x: int

    @precondition(entry_point="epa")
    def epa_pre(state: object, args: AArgs) -> bool:
        return args.x > 0

    @precondition(entry_point="epb")
    def epb_pre(state: object, args: AArgs) -> bool:
        return args.x < 0

    result = render_all()
    assert "[epa]" in result
    assert "[epb]" in result
    assert "args.x > 0" in result
    assert "args.x < 0" in result


def test_render_all_empty():
    assert render_all() == "No contracts registered."


def test_contract_with_not_operator_math():
    @dataclass(frozen=True)
    class NotArgs(Args):
        flag: bool

    @precondition(entry_point="not_test")
    def not_test_pre(state: object, args: NotArgs) -> bool:
        return not args.flag

    result = render_precondition("not_test", mode="math")
    assert "¬(" in result
    assert "args.flag" in result


def test_quantifier_with_exists():
    @dataclass(frozen=True)
    class ExArgs(Args):
        xs: list

    @precondition(entry_point="ex")
    def ex_pre(state: object, args: ExArgs) -> bool:
        from specsaver import exists

        return exists(args.xs, lambda x: x > 0)

    result = render_precondition("ex", mode="math")
    assert "∃" in result
    assert "x > 0" in result
