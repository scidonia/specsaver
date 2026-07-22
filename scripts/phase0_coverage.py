"""Phase 0 coverage spike — what fraction of existing contract clauses
can axiomander's ContractLinter + contract_ir_iris compile today?

For every predicate in both example domains (bank_transfer, inventory),
extract the lambda source (the render pipeline's extraction), lint it
to contract_ir, then compile via contract_ir_iris.  Classify:

  FULL        — lints and compiles to a nontrivial Coq Prop
  TRIVIALIZED — lints but iris_prop returns `True` (phase-3 node)
  UNSUPPORTED — linter rejects (violations) or produces no IR

Run: PYTHONPATH=src:. uv run python scripts/phase0_coverage.py
"""

from __future__ import annotations

import ast
from collections import defaultdict

from specsaver.backend.contract_ir_iris import _collect_vars, iris_prop
from specsaver.backend.contract_linter import ContractLinter
from specsaver.render import _extract_return_expression_with_params


def _contracts():
    from examples.bank_transfer.contract import transfer_contract
    from examples.inventory.contract import (
        release_contract,
        reserve_contract,
        restock_contract,
    )

    return {
        "transfer": transfer_contract,
        "reserve": reserve_contract,
        "release": release_contract,
        "restock": restock_contract,
    }


def _clauses(contract):
    """Yield (kind, predicate) pairs for every clause in a contract."""
    for p in contract.requires:
        yield "requires", p
    for p in contract.ensures:
        yield "ensures", p
    for p in contract.invariants:
        yield "invariant", p
    for exit_ in contract.exceptions:
        for p in exit_.when:
            yield f"exc.when[{exit_.raises.__name__}]", p
        for p in exit_.ensures:
            yield f"exc.ensures[{exit_.raises.__name__}]", p
    for name, fn in contract.derives.items():
        yield f"derives[{name}]", fn


def classify(src: str, params: tuple[str, ...]) -> tuple[str, str]:
    """Return (status, detail) for one predicate source."""
    try:
        node = ast.parse(src, mode="eval").body
    except SyntaxError as exc:
        return "UNSUPPORTED", f"parse: {exc}"
    linter = ContractLinter(params=list(params))
    result = linter.lint_expression(node)
    if result.ir is None:
        kinds = {getattr(v, "kind", "?") for v in result.violations}
        return "UNSUPPORTED", ",".join(str(k) for k in kinds) or "no-ir"
    ir_type = type(result.ir).__name__
    if ir_type == "OpaqueTerm":
        return "OPAQUE", ir_type
    try:
        prop = iris_prop(result.ir)
    except Exception as exc:
        return "UNSUPPORTED", f"iris_prop: {type(exc).__name__}"
    if prop.strip() == "True":
        return "TRIVIALIZED", ir_type
    # Vacuity check: every meaningful clause mentions at least one
    # variable.  If the IR is variable-free, the compilation silently
    # trivialized the clause to a literal — worse than rejection,
    # because it looks like success.
    if not _collect_vars(result.ir):
        return "VACUOUS", ir_type
    return "FULL", ir_type


def main() -> None:
    rows = []
    for cname, contract in _contracts().items():
        for kind, pred in _clauses(contract):
            src, params = _extract_return_expression_with_params(pred)
            if src is None:
                rows.append((cname, kind, "UNSUPPORTED", "no-source",
                             getattr(pred, "__qualname__", "?")))
                continue
            status, detail = classify(src, params)
            snippet = src if len(src) <= 60 else src[:57] + "..."
            rows.append((cname, kind, status, detail, snippet))

    counts: dict[tuple[str, str], int] = defaultdict(int)
    kinds_by_status: dict[str, set] = defaultdict(set)
    for cname, _kind, status, detail, _ in rows:
        counts[cname, status] += 1
        kinds_by_status[status].add(detail)

    statuses = ("FULL", "OPAQUE", "VACUOUS", "TRIVIALIZED", "UNSUPPORTED")
    print(f"{'contract':<12} {'FULL':>5} {'OPAQ':>5} {'VAC':>5} {'TRIV':>5}"
          f" {'UNSUP':>6} {'total':>6}")
    for cname in _contracts():
        vals = [counts[cname, s] for s in statuses]
        print(f"{cname:<12} {vals[0]:>5} {vals[1]:>5} {vals[2]:>5}"
              f" {vals[3]:>5} {vals[4]:>6} {sum(vals):>6}")
    totals = [sum(counts[c, s] for c in _contracts()) for s in statuses]
    print(f"{'TOTAL':<12} {totals[0]:>5} {totals[1]:>5} {totals[2]:>5}"
          f" {totals[3]:>5} {totals[4]:>6} {sum(totals):>6}")
    print()
    for status in statuses:
        print(f"{status}: {sorted(kinds_by_status[status])}")
    print()
    print(f"{'contract':<10} {'kind':<34} {'status':<12} {'ir':<14} clause")
    for cname, kind, status, detail, snippet in rows:
        mark = {"FULL": "+", "OPAQUE": "o", "VACUOUS": "v",
                "TRIVIALIZED": "~", "UNSUPPORTED": "-"}[status]
        print(f"{mark} {cname:<9} {kind:<34} {status:<12} {detail:<14} {snippet}")


if __name__ == "__main__":
    main()
