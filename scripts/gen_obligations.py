"""Generate proof obligations for a contract and score them.

Usage:
  PYTHONPATH=src:. uv run python scripts/gen_obligations.py \\
      examples.inventory.contract reserve_contract \\
      examples.inventory.types Product products sku

  PYTHONPATH=src:. uv run python scripts/gen_obligations.py \\
      --layered \\
      examples.inventory.contract reserve_contract \\
      examples.inventory.types Product products sku
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

from specsaver.lower.emit import emit_contract, emit_layered
from specsaver.lower.harness import _compile_file_in_dir, score
from specsaver.lower.introspect import introspect_contract


def _compile_project_files(out_dir: Path) -> None:
    """Compile all .v files listed in the _CoqProject in order.

    coqc picks up dependencies from .vo files in the same directory,
    so compiling in _CoqProject order guarantees each file's deps
    are ready before it's its turn.
    """
    coqproject = out_dir / "_CoqProject"
    if not coqproject.exists():
        return
    for line in coqproject.read_text().strip().splitlines():
        stripped = line.strip()
        if not stripped or stripped[0] in (None, "-", "#"):
            continue
        vf = out_dir / stripped
        if vf.suffix == ".v" and vf.exists():
            proc = _compile_file_in_dir(vf)
            if proc.returncode != 0:
                err = proc.stderr.split("\n")[0] if proc.stderr else "?"
                print(f"  compile error {vf.name}: {err}")


def main() -> int:
    args = sys.argv[1:]
    layered = False
    counter = False
    while args and args[0].startswith("--"):
        if args[0] == "--layered":
            layered = True
        elif args[0] == "--counter":
            counter = True
        args = args[1:]
    if len(args) < 6:
        print("usage: gen_obligations.py [--layered] [--counter] "
              "<module> <contract> <types_module> <row_type> <map_field> "
              "<key_arg>")
        return 1
    module_name, contract_name, types_name, row_name, map_field, key_arg = args[:6]
    contract = getattr(importlib.import_module(module_name), contract_name)
    row_type = getattr(importlib.import_module(types_name), row_name)

    info = introspect_contract(contract, row_type, map_field, key_arg)
    deltas = ", ".join(f"{d.key_arg}.{d.field}{d.op}args.{d.qty_arg}"
                       for d in info.deltas)
    print(f"introspected [{info.name}]: fields={info.row_fields} "
          f"deltas=[{deltas}] scalars={info.scalars} "
          f"exits={[e.name for e in info.exits]}")

    source = f"{module_name}:{contract_name}"

    if layered:
        witnesses = None
        if counter:
            # Collect authored witnesses from the contract module, if any.
            # Convention: <CONTRACT_MODULE>_WITNESS or a module-level
            # FALSE_*_WITNESS list/dict in runner-JSON form.
            mod = importlib.import_module(module_name)
            witnesses = []
            for attr in dir(mod):
                if attr.endswith("_WITNESS"):
                    w = getattr(mod, attr)
                    if isinstance(w, dict):
                        witnesses.append(w)
                    elif isinstance(w, list):
                        witnesses.extend(w)
            print(f"counter-example mode: {len(witnesses)} "
                  f"candidate witness(es) found")
        out_dir = Path("coqgen") / info.name
        emit_layered(info, source, str(out_dir), counter_witnesses=witnesses)
        print(f"emitted layered to {out_dir}/")
        # Compile all files in _CoqProject order before scoring.
        _compile_project_files(out_dir)
        # Score each layer file — the scoreboard is now three-valued
        # (PROVED / DISPROVED / UNKNOWN) with Lneg detection.
        unknown = 0
        for layer_v in sorted(out_dir.glob(f"{info.name}_L*.v")):
            board = score(layer_v)
            print(f"scoreboard ({layer_v.name}):\n{board.report()}")
            unknown += sum(1 for s in board.results.values() if s == "UNKNOWN")
    else:
        text = emit_contract(info, source)
        out_dir = Path("coqgen")
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
