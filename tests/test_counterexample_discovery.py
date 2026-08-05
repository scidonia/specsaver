"""Implementation-yielded counter-example discovery.

The unguarded reserve implementation writes reserved above on_hand,
so the runner detects the invariant violation and we package the
witness from the implementation's own behavior — no hand-authored
witness.  See docs/proof-counterexample-workflow.md §7.
"""

from examples.inventory.contract_unguarded import (
    FAILING_ROW,
    discover_witness,
    reserve_unguarded_contract,
)
from examples.inventory.types import Product
from specsaver.lower.emit import emit_layered
from specsaver.lower.introspect import introspect_contract


def test_discover_witness_finds_violation():
    """The unguarded impl breaks the invariant; the witness is packaged."""
    w = discover_witness(FAILING_ROW)
    assert w is not None
    assert w["obligation"] == "invariant_preservation"
    assert w["args"] == ["SKU1", "ORDER1", 5]
    assert w["store"]["SKU1"]["reserved"] == 8
    assert w["computed"]["reserved"] == 13
    assert w["computed"]["reserved"] > w["computed"]["on_hand"]


def test_no_witness_for_safe_row():
    """A row within stock does not produce a witness."""
    safe = dict(FAILING_ROW, quantity="2")
    assert discover_witness(safe) is None


def test_no_witness_when_pre_fails():
    """Admissibility failure (qty <= 0) is not an invariant violation."""
    bad = dict(FAILING_ROW, quantity="0")
    assert discover_witness(bad) is None


def test_emitted_lneg_compiles(tmp_path):
    """The discovered witness materializes into a compilable Lneg layer."""
    w = discover_witness(FAILING_ROW)
    assert w is not None
    info = introspect_contract(
        reserve_unguarded_contract, Product, "products", "sku",
    )
    emit_layered(
        info,
        "examples.inventory.contract_unguarded:reserve_unguarded_contract",
        str(tmp_path),
        counter_witnesses=[w],
    )
    lneg = tmp_path / "reserve_Lneg.v"
    assert lneg.exists()
    text = lneg.read_text()
    assert "CounterWitness" in text
    assert "cex_0" in text
    assert "preservation_negation_form" in text
    assert "preservation_false" in text
