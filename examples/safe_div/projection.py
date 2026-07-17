"""Safe division — projection layer (no DB, pure computation)."""

from __future__ import annotations

from dataclasses import dataclass

from examples.safe_div.types import DivArgs, DivDerived, DivObserved, DivState


class DivProjection:
    def snapshot(self, state: DivObserved) -> DivState:
        return DivState(observed=state, derived=DivDerived(valid=True))


@dataclass
class DivScenarioWitness:
    args: DivArgs


def build_witness(row: dict[str, str]) -> DivScenarioWitness:
    dividend = int(row["dividend"])
    divisor = int(row["divisor"])
    return DivScenarioWitness(args=DivArgs(dividend=dividend, divisor=divisor))
