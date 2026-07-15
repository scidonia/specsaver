# specsaver

Specification-driven verification toolchain. The contract language is the single
source of semantic truth from which all testing and verification artefacts are
derived.

## Project map

- `src/specsaver/` — Python package: contract language implementation.
- `docs/` — Architecture and language specification.
- `examples/` — Worked examples using the contract language.
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
