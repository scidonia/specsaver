#!/usr/bin/env bash
# Build the Coq stack in dependency order (mirrors axiomander CI).
# Requires: coqc on PATH (opam switch rocq-9, or nix dev shell).
set -euo pipefail
cd "$(dirname "$0")/.."

FILES=(
  coq/ListPredicates.v
  coq/DictModel.v
  coq/SnakeletLang.v
  coq/SnakeletEval.v
  coq/SnakeletExnLang.v
  coq/SnakeletExnWp.v
  coq/SnakeletExnTactics.v
  coq/SnakeletExnDemo.v
  coq/SnakeletExnSpecSDemo.v
  coq/SpecPrelude.v
  coq/ReserveLowering.v
)

for f in "${FILES[@]}"; do
  echo "coqc $f"
  coqc -R coq "" "$f"
done
echo "all coq artifacts compiled"
