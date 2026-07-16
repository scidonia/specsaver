"""specsaver — Specification-driven verification toolchain."""

from specsaver.args import Args, Result
from specsaver.binding import bind_call
from specsaver.contract import (
    effect,
    exceptional,
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
from specsaver.logic import implies
from specsaver.protocols import (
    ExecutionContext,
    FaultInjector,
    ImplementationAdapter,
    ScenarioMaterializer,
    ScenarioWitness,
    SpecificationProjection,
    SpecState,
)
from specsaver.purity import PurityError, check_purity
from specsaver.quantifiers import exists, forall
from specsaver.registry import (
    ContractRecord,
    ContractRegistry,
    ProofStatus,
    get_registry,
)
from specsaver.render import (
    render_all,
    render_contract,
    render_entry_point,
    render_exceptional,
    render_invariant,
    render_postcondition,
    render_precondition,
)
from specsaver.runner import ScenarioAssertionError, ScenarioResult, run_scenario
from specsaver.scenario import GherkinStepTemplate, ScenarioSpecError, SpecScenario
from specsaver.temporal import old, unchanged
from specsaver.types import ContractKind, EffectSpec, Event, Field, Frame
from specsaver.verify import (
    ContractCheck,
    EntryPointResult,
    check_by_feature,
    check_invariants,
    check_postconditions,
    check_preconditions,
    run_checks,
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
    "exceptional",
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
    "implies",
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
    # scenario assembler
    "SpecScenario",
    "ScenarioSpecError",
    "GherkinStepTemplate",
    # scenario runner
    "run_scenario",
    "ScenarioResult",
    "ScenarioAssertionError",
    # protocols
    "ExecutionContext",
    "FaultInjector",
    "ImplementationAdapter",
    "ScenarioMaterializer",
    "ScenarioWitness",
    "SpecificationProjection",
    "SpecState",
    # entry-point verification
    "ContractCheck",
    "EntryPointResult",
    "check_preconditions",
    "check_postconditions",
    "check_invariants",
    "run_entry_point",
    "run_checks",
    "check_by_feature",
    "bind_call",
    # rendering
    "render_precondition",
    "render_postcondition",
    "render_invariant",
    "render_exceptional",
    "render_contract",
    "render_entry_point",
    "render_all",
]
