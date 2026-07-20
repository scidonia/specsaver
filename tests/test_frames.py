"""Tests for specsaver.frames — semantic frame conditions."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from specsaver.contract_model import StateField
from specsaver.frames import (
    check_derived,
    check_frame,
    parse_write_path,
)


@dataclass
class _Row:
    on_hand: int
    reserved: int
    reorder_point: int


@dataclass(frozen=True)
class _Args:
    sku: str
    quantity: int


@dataclass(frozen=True)
class _Observed:
    products: dict
    log: tuple = ()


@dataclass(frozen=True)
class _Derived:
    total: int = 0


@dataclass(frozen=True)
class _State:
    observed: _Observed
    derived: _Derived = field(default_factory=_Derived)


_SCHEMA = {
    "products": StateField(type_hint="dict", provenance="observed"),
    "log": StateField(type_hint="tuple", provenance="observed"),
    "total": StateField(type_hint="int", provenance="derived"),
}

_ARGS = _Args(sku="S1", quantity=5)


def _state(products, log=(), total=0):
    return _State(observed=_Observed(products=products, log=log),
                  derived=_Derived(total=total))


def _p(sku, on_hand=10, reserved=2, reorder=3):
    return _Row(on_hand=on_hand, reserved=reserved, reorder_point=reorder)


# ---------------------------------------------------------------------------
# Path parsing
# ---------------------------------------------------------------------------


def test_parse_bare_field():
    p = parse_write_path("state.reservation_log")
    assert (p.field, p.key, p.attr) == ("reservation_log", None, None)


def test_parse_keyed_row():
    p = parse_write_path("state.products[sku]")
    assert (p.field, p.key, p.attr) == ("products", "sku", None)


def test_parse_keyed_attr():
    p = parse_write_path("state.products[sku].reserved")
    assert (p.field, p.key, p.attr) == ("products", "sku", "reserved")


def test_parse_malformed():
    with pytest.raises(ValueError, match="malformed write path"):
        parse_write_path("products[sku].reserved")
    with pytest.raises(ValueError, match="malformed write path"):
        parse_write_path("state.products[0].reserved")


# ---------------------------------------------------------------------------
# Frame checking
# ---------------------------------------------------------------------------


def test_bare_field_may_change():
    before = _state({"S1": _p("S1")}, log=())
    after = _state({"S1": _p("S1")}, log=("e1",))
    assert check_frame(_SCHEMA, {"state.log"}, before, _ARGS, after) == []


def test_unwritten_field_must_not_change():
    before = _state({"S1": _p("S1")}, log=())
    after = _state({"S1": _p("S1")}, log=("e1",))
    violations = check_frame(_SCHEMA, set(), before, _ARGS, after)
    assert violations == ["state.log changed outside the frame"]


def test_keyed_attr_write_allowed():
    before = _state({"S1": _p("S1", reserved=2)})
    after = _state({"S1": _p("S1", reserved=7)})
    writes = {"state.products[sku].reserved"}
    assert check_frame(_SCHEMA, writes, before, _ARGS, after) == []


def test_sibling_attr_on_same_key_caught():
    before = _state({"S1": _p("S1", on_hand=10, reserved=2)})
    after = _state({"S1": _p("S1", on_hand=99, reserved=7)})
    writes = {"state.products[sku].reserved"}
    violations = check_frame(_SCHEMA, writes, before, _ARGS, after)
    assert violations == [
        "state.products['S1'].on_hand changed outside the frame"
    ]


def test_other_key_caught():
    before = _state({"S1": _p("S1"), "S2": _p("S2", reserved=2)})
    after = _state({"S1": _p("S1", reserved=7), "S2": _p("S2", reserved=9)})
    writes = {"state.products[sku].reserved"}
    violations = check_frame(_SCHEMA, writes, before, _ARGS, after)
    # No attrs written for S2 — the whole row must be equal.
    assert violations == [
        "state.products['S2'] changed outside the frame"
    ]


def test_key_insertion_caught():
    before = _state({"S1": _p("S1")})
    after = _state({"S1": _p("S1", reserved=7), "S9": _p("S9")})
    writes = {"state.products[sku].reserved"}
    violations = check_frame(_SCHEMA, writes, before, _ARGS, after)
    assert len(violations) == 1
    assert "key set changed" in violations[0]


def test_whole_row_write_allowed_for_that_key_only():
    before = _state({"S1": _p("S1"), "S2": _p("S2")})
    after = _state({"S1": _p("S1", on_hand=0, reserved=0, reorder=0),
                    "S2": _p("S2")})
    writes = {"state.products[sku]"}
    assert check_frame(_SCHEMA, writes, before, _ARGS, after) == []


def test_derived_fields_are_not_framed():
    before = _state({"S1": _p("S1")}, total=10)
    after = _state({"S1": _p("S1")}, total=999)
    assert check_frame(_SCHEMA, set(), before, _ARGS, after) == []


# ---------------------------------------------------------------------------
# Derived consistency
# ---------------------------------------------------------------------------


def test_derived_consistent():
    after = _state({"S1": _p("S1", on_hand=10)}, total=10)
    derives = {"total": lambda s: sum(
        p.on_hand for p in s.observed.products.values())}
    assert check_derived(derives, after) == []


def test_derived_drift_caught():
    after = _state({"S1": _p("S1", on_hand=10)}, total=999)
    derives = {"total": lambda s: sum(
        p.on_hand for p in s.observed.products.values())}
    violations = check_derived(derives, after)
    assert len(violations) == 1
    assert "drift" in violations[0] or "projection says" in violations[0]
