"""specsaver — Specification-driven verification toolchain."""

from specsaver.args import Args, Result
from specsaver.binding import bind_call
from specsaver.contract import (
    effect,
    function,
    ghost,
    ghost_update,
    invariant,
    measure,
    postcondition,
    precondition,
    predicate,
    reads,
    writes,
)
from specsaver.ghost_state import GhostState
from specsaver.purity import PurityError, check_purity
from specsaver.quantifiers import exists, forall
from specsaver.registry import (
    ContractRecord,
    ContractRegistry,
    ProofStatus,
    get_registry,
)
from specsaver.temporal import old, unchanged
from specsaver.types import ContractKind, EffectSpec, Event, Field, Frame
from specsaver.verify import (
    ContractCheck,
    EntryPointResult,
    check_invariants,
    check_postconditions,
    check_preconditions,
    run_entry_point,
)

__all__ = [
    # decorators
    "precondition",
    "postcondition",
    "invariant",
    "predicate",
    "function",
    "writes",
    "reads",
    "effect",
    "ghost",
    "ghost_update",
    "measure",
    "ContractKind",
    # canonical args/result
    "Args",
    "Result",
    # types
    "Frame",
    "Field",
    "Event",
    "EffectSpec",
    # quantifiers
    "forall",
    "exists",
    # temporal
    "old",
    "unchanged",
    # registry
    "ContractRecord",
    "ContractRegistry",
    "ProofStatus",
    "get_registry",
    # ghost
    "GhostState",
    # purity
    "check_purity",
    "PurityError",
    # entry-point verification
    "ContractCheck",
    "EntryPointResult",
    "check_preconditions",
    "check_postconditions",
    "check_invariants",
    "run_entry_point",
    "bind_call",
]
