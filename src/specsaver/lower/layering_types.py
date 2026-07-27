"""Layered obligation emission — types for the emission verification domain.

The "state" is the filesystem after emit_layered runs: a directory
of .v files, a _CoqProject, and a schedule.json.  The contract verifies
that the emitted structure matches the expected dependency layering.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class EmitArgs:
    module: str
    contract: str
    types_module: str
    row_type: str
    map_field: str
    key_arg: str


@dataclass(frozen=True)
class EmitReceipt:
    out_dir: str
    num_layers: int
    num_files: int


class EmitError(Exception):
    code: str = "EMIT_ERROR"


class UnsupportedShapeEmitError(EmitError):
    code = "UNSUPPORTED_SHAPE"


@dataclass(frozen=True)
class EmitObserved:
    layer_files: Mapping[str, str]   # filename -> content text
    schedule: dict                   # parsed schedule.json
    coq_project: list[str]           # lines of _CoqProject
    compilation: dict[str, bool]     # filename -> compiled successfully?


@dataclass(frozen=True)
class EmitDerived:
    total_files: int
    num_layers: int
    all_compiled: bool


@dataclass(frozen=True)
class EmitGhost:
    pass


@dataclass(frozen=True)
class EmitSpecState:
    observed: EmitObserved
    derived: EmitDerived
    ghost: EmitGhost = field(default_factory=EmitGhost)
