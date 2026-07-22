# specsaver

Specification-driven verification toolchain. The contract language is the single
source of semantic truth from which all testing and verification artefacts are
derived.

## Project map

- `src/specsaver/` — Python package: contract language implementation,
  frame checker, generic scenario runner, and library theories
  (`specsaver.theory` — SQL database theory; logging/OTel to follow).
  The theory ships a DBAPI shim (`make_engine`) so services written
  against SQLAlchemy run unchanged on the stub engine.
- `src/specsaver/backend/` — proof machinery imported from axiomander:
  `contract_ir`, `contract_linter`, `contract_ir_iris`, `shape_ir`
  (keep upstream style for easy sync — lint is relaxed for these files).
- `src/specsaver/lower/` — obligation generator: introspects a
  `Contract` and emits a Coq obligation file (`scripts/gen_obligations.py`
  drives it; `specsaver.lower.harness` compiles + scoreboards).
- `coq/` — Snakelet language + WP calculus + FunSpecS kernel
  (`scripts/build_coq.sh` builds in dependency order; needs coqc from
  the opam rocq-9 switch until nix rocq deps land).
- `stubs/` — `.pyi` library stub contracts (adornment complement to
  the theories).
- `docs/` — Architecture and language specification.
- `examples/` — Worked examples using the contract language. Services
  are written against SQLAlchemy (`engine.begin()` for transactions);
  scenario materializers use real SQLite files, the theory uses the
  stub engine.
- `scripts/` — `phase0_coverage.py` (coverage spike), `build_coq.sh`.
- `tests/` — Pytest suite.

## Dev shell

```bash
direnv allow      # activate nix dev shell
uv sync           # install deps
uv run pytest     # run tests
```

## Rules

- Never push unless explicitly asked.
- Run `uv run pytest` after every change.
- Run `uv run ruff check .` to lint.
