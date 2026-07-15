"""Framework Protocols for symmetric specification-driven testing.

These are the interfaces the generic runner depends on.  Each domain
provides concrete implementations — the framework never instantiates
these directly.

See docs/Specification-Driven-Testing-Architecture.md §5–6 and the
Symmetric Database State document §19.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ExecutionContext(Protocol):
    """The concrete execution world: database, environment, trace, ghost.

    Domains provide a concrete dataclass implementing this.  The runner
    passes it to ``materialize`` (to create it), ``snapshot`` (to
    project it), and ``impl.execute`` (to run the implementation on it).
    """

    database: Any
    environment: Any
    trace: Any
    ghost: Any


@runtime_checkable
class SpecState(Protocol):
    """Immutable contract-facing snapshot of the execution context.

    Domains provide a concrete frozen dataclass with provenance
    decomposition (observed, derived, environment, history, ghost).
    """


@runtime_checkable
class ScenarioWitness(Protocol):
    """Abstract initial state + args, produced from a Gherkin Examples row.

    Domains provide a concrete frozen dataclass.  The materializer
    consumes it to create an ExecutionContext; the projection must
    agree with it after materialization (materialization agreement law).
    """

    args: Any


@runtime_checkable
class SpecificationProjection(Protocol):
    """Projects an ExecutionContext into an immutable SpecState.

    The same projection must be used before and after execution
    (symmetry requirement, §6 of the Symmetric document).
    """

    def snapshot(self, context: ExecutionContext) -> SpecState:
        ...


@runtime_checkable
class ScenarioMaterializer(Protocol):
    """Creates a concrete ExecutionContext from a ScenarioWitness."""

    def materialize(self, witness: ScenarioWitness) -> ExecutionContext:
        ...


@runtime_checkable
class ImplementationAdapter(Protocol):
    """Executes the real implementation on the execution context."""

    def execute(self, context: ExecutionContext, args: Any) -> Any:
        ...


@runtime_checkable
class FaultInjector(Protocol):
    """Injects a named fault before the implementation runs."""

    def inject(self, fault_name: str) -> None:
        ...
