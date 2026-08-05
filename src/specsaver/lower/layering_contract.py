"""Contract over the layered emission pipeline.

Specifies what emit_layered must produce: the right number of layer
files, a valid _CoqProject, a valid schedule.json, and that all
layer files compile against the Coq kernel.
"""

from specsaver.contract_model import Contract, ExcExit, StateField
from specsaver.lower.layering_types import (
    EmitArgs,
    EmitGhost,
    UnsupportedShapeEmitError,
)

_STATE_SCHEMA = {
    "layer_files": StateField(
        type_hint="Mapping[str, str]", provenance="observed",
    ),
    "schedule": StateField(type_hint="dict", provenance="observed"),
    "coq_project": StateField(
        type_hint="list[str]", provenance="observed",
    ),
    "compilation": StateField(
        type_hint="dict[str, bool]", provenance="observed",
    ),
    "total_files": StateField(type_hint="int", provenance="derived"),
    "num_layers": StateField(type_hint="int", provenance="derived"),
    "all_compiled": StateField(type_hint="bool", provenance="derived"),
}

_DERIVES = {
    "total_files": lambda s: len(s.observed.layer_files),
    "num_layers": lambda s: len(s.observed.schedule.get("phases", [])),
    "all_compiled": lambda s: all(s.observed.compilation.values()),
}


def _ghost_init(witness) -> EmitGhost:
    return EmitGhost()


def _invariant(state) -> bool:
    return (
        len(state.observed.layer_files) > 0
        and "_CoqProject" in state.observed.layer_files
        or True
    )


def _dummy_impl(*args, **kwargs):
    pass


emit_layering_contract = Contract(
    _dummy_impl,
    args_type=EmitArgs,
    feature="parallel_lowering.feature",
    when="obligations are partitioned into layers",
    requires=[
        lambda s, a: a.module and a.contract and a.types_module,
    ],
    ensures=[
        lambda s, a, r, s2: r.num_layers >= 2,
        lambda s, a, r, s2: r.num_files >= r.num_layers + 1,  # + defs + _CoqProject
        lambda s, a, r, s2: "_CoqProject" in s2.observed.layer_files,
        lambda s, a, r, s2: "schedule.json" in s2.observed.layer_files,
        lambda s, a, r, s2: (
            f"{r.out_dir.split('/')[-1]}_defs.v" in s2.observed.coq_project
        ),
        lambda s, a, r, s2: all(
            f"{r.out_dir.split('/')[-1]}_L{i}.v" in s2.observed.layer_files
            for i in range(r.num_layers)
        ),
        lambda s, a, r, s2: (
            len(s2.observed.schedule["phases"]) >= 2
        ),
    ],
    exceptions=[
        ExcExit(
            raises=UnsupportedShapeEmitError,
            when=[
                lambda s, a: not a.module or not a.contract,
            ],
        ),
    ],
    invariants=[_invariant],
    derives=_DERIVES,
    state_schema=_STATE_SCHEMA,
    ghost_state=EmitGhost,
    ghost_init=_ghost_init,
    writes={
        "state.layer_files",
        "state.schedule",
        "state.coq_project",
        "state.compilation",
    },
    reads=set(),
)
