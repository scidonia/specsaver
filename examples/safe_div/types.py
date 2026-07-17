"""Safe division domain types."""

from __future__ import annotations

from dataclasses import dataclass, field

from specsaver import Args, Result


@dataclass(frozen=True)
class DivArgs(Args):
    dividend: int
    divisor: int


@dataclass(frozen=True)
class DivResult(Result):
    quotient: int
    remainder: int


class DivisionError(Exception):
    code = "DIVISION_ERROR"


@dataclass(frozen=True)
class DivObserved:
    dividend: int
    divisor: int
    quotient: int | None = None
    remainder: int | None = None


@dataclass(frozen=True)
class DivDerived:
    valid: bool = True


@dataclass(frozen=True)
class DivState:
    observed: DivObserved
    derived: DivDerived = field(default_factory=DivDerived)
