"""Tests for specsaver.binding.bind_call — adapting a canonical Args object
to an arbitrary native Python calling convention.

Covers every kind of parameter Python supports: positional-only,
positional-or-keyword, *args, keyword-only, **kwargs, and default values
(both left at their default and overridden by an Args field).
"""

from dataclasses import dataclass

import pytest

from specsaver import Args, bind_call


@dataclass(frozen=True)
class ThreeFieldArgs(Args):
    a: int
    b: int
    c: int


def test_spread_false_passes_args_object_directly():
    """Default behaviour: impl receives the whole Args object, unchanged."""

    def impl(state, whole_args):
        return (state, whole_args)

    args = ThreeFieldArgs(a=1, b=2, c=3)
    result = bind_call(impl, "STATE", args=args)
    assert result == ("STATE", args)


def test_spread_true_positional_only():
    def impl(state, a, b, /, c):
        return (state, a, b, c)

    args = ThreeFieldArgs(a=1, b=2, c=3)
    result = bind_call(impl, "STATE", args=args, spread=True)
    assert result == ("STATE", 1, 2, 3)


def test_spread_true_keyword_only():
    def impl(state, *, a, b, c):
        return (state, a, b, c)

    args = ThreeFieldArgs(a=1, b=2, c=3)
    result = bind_call(impl, "STATE", args=args, spread=True)
    assert result == ("STATE", 1, 2, 3)


def test_spread_true_defaults_used_when_not_supplied():
    """A parameter with a default and no matching Args field keeps its default."""

    def impl(state, a, b, c, d=99, e=100):
        return (state, a, b, c, d, e)

    args = ThreeFieldArgs(a=1, b=2, c=3)
    result = bind_call(impl, "STATE", args=args, spread=True)
    assert result == ("STATE", 1, 2, 3, 99, 100)


def test_spread_true_defaults_overridden_by_args_field():
    """A parameter with a default IS overridden if Args supplies a matching field."""

    def impl(state, a, b, c, d=99, e=100):
        return (state, a, b, c, d, e)

    @dataclass(frozen=True)
    class FiveFieldArgs(Args):
        a: int
        b: int
        c: int
        d: int
        e: int

    args = FiveFieldArgs(a=1, b=2, c=3, d=7, e=8)
    result = bind_call(impl, "STATE", args=args, spread=True)
    assert result == ("STATE", 1, 2, 3, 7, 8)


def test_spread_true_mixed_defaults_some_used_some_overridden():
    """One default overridden, one left alone, in the same call."""

    def impl(state, a, b, c, d=99, e=100):
        return (state, a, b, c, d, e)

    @dataclass(frozen=True)
    class FourFieldArgs(Args):
        a: int
        b: int
        c: int
        d: int  # overrides the default for d, e is left at its default

    args = FourFieldArgs(a=1, b=2, c=3, d=42)
    result = bind_call(impl, "STATE", args=args, spread=True)
    assert result == ("STATE", 1, 2, 3, 42, 100)


def test_spread_true_var_positional_from_designated_field():
    def impl(state, a, b, c, *rest):
        return (state, a, b, c, rest)

    @dataclass(frozen=True)
    class VarPosArgs(Args):
        a: int
        b: int
        c: int
        extra_positional: tuple = ()

    args = VarPosArgs(a=1, b=2, c=3, extra_positional=(10, 20, 30))
    result = bind_call(
        impl, "STATE", args=args, spread=True, varargs_field="extra_positional"
    )
    assert result == ("STATE", 1, 2, 3, (10, 20, 30))


def test_spread_true_var_positional_empty_when_no_field_given():
    def impl(state, a, b, c, *rest):
        return (state, a, b, c, rest)

    args = ThreeFieldArgs(a=1, b=2, c=3)
    result = bind_call(impl, "STATE", args=args, spread=True)
    assert result == ("STATE", 1, 2, 3, ())


def test_spread_true_var_keyword_from_designated_field():
    def impl(state, a, b, c, **opts):
        return (state, a, b, c, opts)

    @dataclass(frozen=True)
    class VarKwArgs(Args):
        a: int
        b: int
        c: int
        extra_keyword: dict | None = None

    args = VarKwArgs(a=1, b=2, c=3, extra_keyword={"x": 1, "y": 2})
    result = bind_call(
        impl, "STATE", args=args, spread=True, varkwargs_field="extra_keyword"
    )
    assert result == ("STATE", 1, 2, 3, {"x": 1, "y": 2})


def test_spread_true_leftover_fields_flow_into_var_keyword():
    """Args fields not matching any named parameter fall through to **kwargs
    when impl declares one, even without an explicit varkwargs_field."""

    def impl(state, a, **rest):
        return (state, a, rest)

    @dataclass(frozen=True)
    class TwoExtraArgs(Args):
        a: int
        b: int
        c: int

    args = TwoExtraArgs(a=1, b=2, c=3)
    result = bind_call(impl, "STATE", args=args, spread=True)
    state, a, rest = result
    assert (state, a) == ("STATE", 1)
    assert rest == {"b": 2, "c": 3}


def test_spread_true_positional_or_keyword_before_star_args_passed_positionally():
    """A POSITIONAL_OR_KEYWORD parameter before *args must be passed
    positionally, not as a keyword — otherwise the extra *args values would
    collide with its slot.  This is the bug this test guards against."""

    def impl(state, a, b, *rest):
        return (state, a, b, rest)

    @dataclass(frozen=True)
    class BeforeStarArgs(Args):
        a: int
        b: int
        extra: tuple = ()

    args = BeforeStarArgs(a=1, b=2, extra=(10, 20))
    result = bind_call(impl, "STATE", args=args, spread=True, varargs_field="extra")
    assert result == ("STATE", 1, 2, (10, 20))


def test_spread_true_everything_at_once():
    """Positional-only, positional-or-keyword, *args, keyword-only, **kwargs,
    and defaults (used + overridden) all in a single call."""

    def impl(state, a, /, b, *rest, c, d=99, **opts):
        return (state, a, b, rest, c, d, opts)

    @dataclass(frozen=True)
    class EverythingArgs(Args):
        a: int
        b: int
        c: int
        d: int
        rest_field: tuple = ()
        extra: dict | None = None

    args = EverythingArgs(a=1, b=2, c=3, d=4, rest_field=(10, 20), extra={"z": 9})
    result = bind_call(
        impl,
        "STATE",
        args=args,
        spread=True,
        varargs_field="rest_field",
        varkwargs_field="extra",
    )
    assert result == ("STATE", 1, 2, (10, 20), 3, 4, {"z": 9})


def test_spread_true_missing_required_parameter_raises():
    def impl(state, a, b, c, required_but_missing):
        return None  # pragma: no cover

    args = ThreeFieldArgs(a=1, b=2, c=3)
    with pytest.raises(TypeError, match="required_but_missing"):
        bind_call(impl, "STATE", args=args, spread=True)


def test_spread_true_leftover_fields_without_var_keyword_raises():
    def impl(state, a):
        return None  # pragma: no cover

    @dataclass(frozen=True)
    class LeftoverArgs(Args):
        a: int
        unused_field: int = 0

    args = LeftoverArgs(a=1, unused_field=5)
    with pytest.raises(TypeError, match="unused_field"):
        bind_call(impl, "STATE", args=args, spread=True)


def test_spread_true_default_before_star_args_cannot_be_skipped():
    """A POSITIONAL_OR_KEYWORD parameter with a default, sitting before a
    *args parameter that IS being fed via varargs_field, cannot safely be
    left at its default — that would leave an unfillable gap in the
    positional sequence.  This must raise rather than silently misbind."""

    def impl(state, a, b=1, *rest):
        return (state, a, b, rest)  # pragma: no cover

    @dataclass(frozen=True)
    class SkipArgs(Args):
        a: int
        extra: tuple = ()

    args = SkipArgs(a=1, extra=(10, 20))
    with pytest.raises(TypeError, match="'b'"):
        bind_call(impl, "STATE", args=args, spread=True, varargs_field="extra")


def test_spread_true_with_no_leading_state():
    """bind_call works with zero leading positional arguments too."""

    def impl(a, b, c):
        return (a, b, c)

    args = ThreeFieldArgs(a=1, b=2, c=3)
    result = bind_call(impl, args=args, spread=True)
    assert result == (1, 2, 3)
