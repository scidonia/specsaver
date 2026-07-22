"""Generate proof obligations for a contract and score them.

Usage:
  PYTHONPATH=src:. uv run python scripts/gen_obligations.py \
      examples.inventory.contract reserve_contract \
      examples.inventory.types Product products sku
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

from specsaver.lower.emit import emit_contract
from specsaver.lower.harness import score
from specsaver.lower.introspect import introspect_contract


def main() -> int:
    module_name, contract_name, types_name, row_name, map_field, key_arg = (
        sys.argv[1:7]
    )
    contract = getattr(importlib.import_module(module_name), contract_name)
    row_type = getattr(importlib.import_module(types_name), row_name)

    info = introspect_contract(contract, row_type, map_field, key_arg)
    deltas = ", ".join(f"{d.key_arg}.{d.field}{d.op}args.{d.qty_arg}"
                       for d in info.deltas)
    print(f"introspected [{info.name}]: fields={info.row_fields} "
          f"deltas=[{deltas}] scalars={info.scalars} "
          f"exits={[e.name for e in info.exits]}")

    source = f"{module_name}:{contract_name}"
    text = emit_contract(info, source)

    out_dir = Path("coq/gen")
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"Gen{info.name.capitalize()}Obligations.v"
    out.write_text(text)
    print(f"emitted {out}")

    board = score(out)
    print(board.report())
    unknown = [n for n, s in board.results.items() if s != "PROVED"]
    return 1 if unknown else 0


if __name__ == "__main__":
    sys.exit(main())
