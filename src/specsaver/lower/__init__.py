"""Obligation generation — contracts to Coq proof obligations.

The system: introspect a specsaver Contract (row fields, key arg,
delta pattern, availability from exception exits, exception arms),
emit a Coq file in the shapes proven by the hand-lowered
ReserveLowering.v, compile it, and report a per-obligation scoreboard
(PROVED / UNKNOWN).

v1 supports the example-domain contract shape:
  - one observed map of int-fielded records (products/accounts)
  - a keyed delta update (`field' = field ± arg`)
  - scalar requires on args
  - exception arms whose `when` are comparisons over the same row
  - an invariant over row fields
"""

from specsaver.lower.introspect import (
    ContractInfo,
    ExitInfo,
    UnsupportedShapeError,
    introspect_contract,
)

__all__ = [
    "ContractInfo",
    "ExitInfo",
    "UnsupportedShapeError",
    "introspect_contract",
]
