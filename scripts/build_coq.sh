#!/usr/bin/env bash
# Build the Coq stack in dependency order (mirrors axiomander CI).
# Requires: coqc on PATH (opam switch rocq-9, or nix dev shell).
set -euo pipefail
cd "$(dirname "$0")/.."

FILES=(
  coq/ListPredicates.v
  coq/DictModel.v
  coq/SnakeletLang.v
  coq/SnakeletExnLang.v
  coq/SnakeletExnWp.v
  coq/SpecPrelude.v
  coq/SnakeletEval.v
  coq/SnakeletExnPartial.v
  coq/SnakeletExnTactics.v
  coq/SnakeletExnDemo.v
  coq/SnakeletExnSpecSDemo.v
  coq/ReserveLowering.v
  coq/ReleaseLowering.v
  coq/AddOneLowering.v
  coq/DictLowering.v
  coq/ComputeAvailableLowering.v
  coq/WithdrawLowering.v
  coq/FullRestockLowering.v
)

for f in "${FILES[@]}"; do
  echo "coqc $f"
  coqc -R coq "" "$f"
done
echo "all coq artifacts compiled"
