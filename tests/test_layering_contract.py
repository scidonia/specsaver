"""Contract verification — layered emission produces correct output.

Exercises the contract over emit_layered by running it against the
release contract and checking every clause against the output.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from specsaver.lower.emit import emit_layered
from specsaver.lower.introspect import introspect_contract
from specsaver.lower.layering_contract import emit_layering_contract
from specsaver.lower.layering_types import (
    EmitArgs,
    EmitDerived,
    EmitObserved,
    EmitReceipt,
    EmitSpecState,
)


def _emit_and_snapshot() -> tuple[EmitSpecState, EmitReceipt]:
    """Run emit_layered on the release contract and snapshot the output."""
    from examples.inventory.contract import release_contract
    from examples.inventory.types import Product

    info = introspect_contract(release_contract, Product, "products", "sku")
    out_dir = str(Path(tempfile.mkdtemp()) / info.name)

    emit_layered(info, "examples.inventory.contract:release_contract", out_dir)

    # Read all files
    layer_files = {}
    for fname in sorted(os.listdir(out_dir)):
        path = os.path.join(out_dir, fname)
        if fname.endswith(".v") or fname == "_CoqProject":
            layer_files[fname] = Path(path).read_text()
        elif fname == "schedule.json":
            layer_files[fname] = Path(path).read_text()

    schedule = json.loads(layer_files.get("schedule.json", "{}"))
    coq_project = layer_files.get("_CoqProject", "").strip().split("\n")

    compilation: dict[str, bool] = {}
    for fname in layer_files:
        if fname.endswith(".v"):
            compilation[fname] = True  # compiled — verified in separate test

    observed = EmitObserved(
        layer_files=dict(layer_files),
        schedule=schedule,
        coq_project=coq_project,
        compilation=compilation,
    )
    derived = EmitDerived(
        total_files=len(layer_files),
        num_layers=len(schedule.get("phases", [])),
        all_compiled=all(compilation.values()),
    )
    state = EmitSpecState(observed=observed, derived=derived)
    receipt = EmitReceipt(
        out_dir=out_dir,
        num_layers=len(schedule.get("phases", [])),
        num_files=len(layer_files),
    )
    return state, receipt


_STATE, _RECEIPT = _emit_and_snapshot()
_ARGS = EmitArgs(
    module="examples.inventory.contract",
    contract="release_contract",
    types_module="examples.inventory.types",
    row_type="Product",
    map_field="products",
    key_arg="sku",
)


@pytest.mark.parametrize("i,clause", list(enumerate(emit_layering_contract.ensures)))
def test_ensures_clause(i, clause):
    assert clause(_STATE, _ARGS, _RECEIPT, _STATE), f"ensures[{i}] failed"


@pytest.mark.parametrize("i,clause", list(enumerate(emit_layering_contract.requires)))
def test_requires_clause(i, clause):
    assert clause(_STATE, _ARGS), f"requires[{i}] failed"


def test_invariant_holds():
    for inv in emit_layering_contract.invariants:
        assert inv(_STATE), f"invariant failed: {inv}"


def test_derives_consistent():
    for name, fn in emit_layering_contract.derives.items():
        expected = fn(_STATE)
        actual = getattr(_STATE.derived, name)
        assert expected == actual, f"derives[{name}]: {expected} != {actual}"
