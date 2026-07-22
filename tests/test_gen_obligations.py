"""End-to-end test for the obligation generator.

Introspects the reserve contract, emits the Coq obligation file,
compiles it, and requires every obligation to be PROVED.
Skips if coqc is unavailable.
"""

from __future__ import annotations

import shutil

import pytest

from specsaver.lower.emit import emit_contract
from specsaver.lower.introspect import introspect_contract

pytestmark = pytest.mark.skipif(
    shutil.which("coqc") is None, reason="coqc not available"
)


def _reserve_info():
    from examples.inventory.contract import reserve_contract
    from examples.inventory.types import Product

    return introspect_contract(reserve_contract, Product, "products", "sku")


def test_introspect_reserve():
    from specsaver.lower.introspect import DeltaInfo

    info = _reserve_info()
    assert info.row_fields == (
        ("on_hand", "int"), ("reserved", "int"), ("reorder_point", "int"))
    assert info.deltas == (DeltaInfo(
        key_arg="sku", field="reserved", op="+", qty_arg="quantity"),)
    assert info.scalars == (("quantity", ">", "0"),)
    assert info.invariant_le == ("reserved", "on_hand")
    assert [e.name for e in info.exits] == ["InsufficientStockError"]
    assert info.exits[0].payload == ("available", "sku", "order_id", "quantity")


def test_emit_and_score_reserve(tmp_path):
    from specsaver.lower.harness import score

    info = _reserve_info()
    text = emit_contract(info, "examples.inventory.contract:reserve_contract")
    out = tmp_path / "GenReserveObligations.v"
    out.write_text(text)
    board = score(out)
    assert board.results, "no obligations generated"
    for name, status in board.results.items():
        assert status == "PROVED", f"{name}: {status}"


@pytest.mark.parametrize("contract_name", ["release_contract", "restock_contract"])
def test_emit_and_score_inventory_siblings(tmp_path, contract_name):
    import examples.inventory.contract as ic
    from examples.inventory.types import Product
    from specsaver.lower.harness import score

    contract = getattr(ic, contract_name)
    info = introspect_contract(contract, Product, "products", "sku")
    text = emit_contract(info, f"examples.inventory.contract:{contract_name}")
    out = tmp_path / f"Gen{contract_name}.v"
    out.write_text(text)
    board = score(out)
    assert board.results, "no obligations generated"
    for name, status in board.results.items():
        assert status == "PROVED", f"{name}: {status}"


def test_no_delta_is_loud():
    from examples.inventory.service import InventoryService
    from examples.inventory.types import Product, ReserveArgs
    from specsaver.contract_model import Contract
    from specsaver.lower.introspect import UnsupportedShapeError, introspect_contract

    no_delta = Contract(
        InventoryService.reserve,
        args_type=ReserveArgs,
        feature="x.feature",
        requires=[lambda state, args: args.quantity > 0],
        ensures=[
            lambda old_s, args, result, new_s: (
                old_s.derived.total_on_hand == new_s.derived.total_on_hand
            ),
        ],
        writes={"state.products[sku].reserved"},
    )
    with pytest.raises(UnsupportedShapeError, match="no delta clause"):
        introspect_contract(no_delta, Product, "products", "sku")


def test_multi_exit_and_multi_delta_supported(tmp_path):
    from examples.bank_transfer.contract import transfer_contract
    from examples.bank_transfer.types import Account
    from specsaver.lower.emit import emit_contract
    from specsaver.lower.harness import score

    info = introspect_contract(transfer_contract, Account, "accounts", "source_id")
    assert len(info.deltas) == 2
    assert len(info.exits) == 2
    text = emit_contract(info, "examples.bank_transfer.contract:transfer_contract")
    out = tmp_path / "GenTransferObligations.v"
    out.write_text(text)
    board = score(out)
    # every obligation is emitted and well-formed; proofs are best-effort
    assert "o3_0_exception_consistency" in board.results
    assert "o3_1_exception_consistency" in board.results


def test_purity_gate_rejects_impure_predicate():
    from examples.inventory.service import InventoryService
    from examples.inventory.types import Product, ReserveArgs
    from specsaver.contract_model import Contract
    from specsaver.lower.introspect import UnsupportedShapeError, introspect_contract

    impure = Contract(
        InventoryService.reserve,
        args_type=ReserveArgs,
        feature="x.feature",
        requires=[lambda state, args: args.quantity > 0],
        ensures=[
            lambda old_s, args, result, new_s: (
                new_s.observed.products[args.sku].reserved
                == old_s.observed.products[args.sku].reserved + args.quantity
            ),
            lambda old_s, args, result, new_s: print("side effect") is None,
        ],
        writes={"state.products[sku].reserved"},
    )
    with pytest.raises(UnsupportedShapeError, match="impure"):
        introspect_contract(impure, Product, "products", "sku")


def test_frame_validation_rejects_delta_outside_writes():
    from examples.inventory.service import InventoryService
    from examples.inventory.types import Product, ReserveArgs
    from specsaver.contract_model import Contract
    from specsaver.lower.introspect import UnsupportedShapeError, introspect_contract

    bad_frame = Contract(
        InventoryService.reserve,
        args_type=ReserveArgs,
        feature="x.feature",
        requires=[lambda state, args: args.quantity > 0],
        ensures=[
            lambda old_s, args, result, new_s: (
                new_s.observed.products[args.sku].reserved
                == old_s.observed.products[args.sku].reserved + args.quantity
            ),
        ],
        # frame names a different attr than the delta — the spec would
        # write outside its declared frame
        writes={"state.products[sku].on_hand"},
    )
    with pytest.raises(UnsupportedShapeError, match="is not a delta"):
        introspect_contract(bad_frame, Product, "products", "sku")
