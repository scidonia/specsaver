from dataclasses import dataclass, field
from enum import Enum, auto


class ContractKind(Enum):
    PRECONDITION = auto()
    POSTCONDITION = auto()
    INVARIANT = auto()
    PREDICATE = auto()
    FUNCTION = auto()
    WRITES = auto()
    READS = auto()
    EFFECT = auto()
    EXCEPTIONAL = auto()
    GHOST = auto()
    GHOST_UPDATE = auto()
    MEASURE = auto()


@dataclass(frozen=True)
class Field:
    """A dotted path to a state component."""

    path: str

    def __post_init__(self) -> None:
        if not self.path or ".." in self.path:
            raise ValueError(f"Invalid field path: {self.path!r}")

    def parent(self) -> "Field | None":
        parts = self.path.rsplit(".", 1)
        if len(parts) == 1:
            return None
        return Field(parts[0])

    def is_prefix_of(self, other: "Field") -> bool:
        return other.path == self.path or other.path.startswith(self.path + ".")

    def __str__(self) -> str:
        return self.path


@dataclass(frozen=True)
class Frame:
    """Declares what an operation may read or write.

    Accepts set or frozenset for writes/reads; stores as frozenset.
    """

    writes: frozenset[Field] | set[Field] = field(default_factory=frozenset)
    reads: frozenset[Field] | set[Field] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        object.__setattr__(self, "writes", frozenset(self.writes))
        object.__setattr__(self, "reads", frozenset(self.reads))

    def __or__(self, other: "Frame") -> "Frame":
        return Frame(
            writes=self.writes | other.writes,
            reads=self.reads | other.reads,
        )


@dataclass(frozen=True)
class Event:
    """An observable event emitted by an operation."""

    name: str

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Event name must not be empty")


@dataclass(frozen=True)
class EffectSpec:
    """Side-effect signature of an operation.

    Accepts set or frozenset for all fields; stores as frozenset.
    """

    opens: frozenset[str] | set[str] = field(default_factory=frozenset)
    uses: frozenset[str] | set[str] = field(default_factory=frozenset)
    closes: frozenset[str] | set[str] = field(default_factory=frozenset)
    emits: frozenset[Event] | set[Event] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        object.__setattr__(self, "opens", frozenset(self.opens))
        object.__setattr__(self, "uses", frozenset(self.uses))
        object.__setattr__(self, "closes", frozenset(self.closes))
        object.__setattr__(self, "emits", frozenset(self.emits))

    def __or__(self, other: "EffectSpec") -> "EffectSpec":
        return EffectSpec(
            opens=self.opens | other.opens,
            uses=self.uses | other.uses,
            closes=self.closes | other.closes,
            emits=self.emits | other.emits,
        )
