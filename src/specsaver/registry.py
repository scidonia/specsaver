"""Contract registry — the global index of all semantic propositions.

Every contract proposition is stored with:
- identifier:  fully-qualified name (<module>.<kind>.<qualname>)
- kind:        precondition, postcondition, invariant, ...
- func:        the Python callable
- module:      source module
- qualname:    qualified name within the module
- status:      proof status (unverified, verified, counterexample)
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from specsaver.types import ContractKind


class ProofStatus(Enum):
    UNVERIFIED = auto()
    VERIFIED = auto()
    COUNTEREXAMPLE = auto()


@dataclass
class ContractRecord:
    identifier: str
    kind: ContractKind
    func: Callable[..., Any]
    module: str
    qualname: str
    status: ProofStatus = ProofStatus.UNVERIFIED
    dependencies: set[str] = field(default_factory=set)
    from_gherkin: str | None = None
    feature: str | None = None
    entry_point: str | None = None

    @property
    def component(self) -> str:
        """Extract component name from the module path."""
        parts = self.module.rsplit(".", 1)
        return parts[-1] if parts else self.module

    @property
    def category(self) -> str:
        return self.kind.name.lower()

    @property
    def name(self) -> str:
        return self.qualname


class ContractRegistry:
    """Thread-safe singleton registry of all contracts."""

    def __init__(self) -> None:
        self._contracts: dict[str, ContractRecord] = {}
        self._entry_point_args_type: dict[str, type] = {}
        self._entry_point_result_type: dict[str, type] = {}
        self._lock = threading.Lock()

    def register(
        self,
        identifier: str,
        kind: ContractKind,
        func: Callable[..., Any],
        module: str,
        qualname: str,
        *,
        from_gherkin: str | None = None,
        feature: str | None = None,
        entry_point: str | None = None,
    ) -> None:
        with self._lock:
            record = ContractRecord(
                identifier=identifier,
                kind=kind,
                func=func,
                module=module,
                qualname=qualname,
                from_gherkin=from_gherkin,
                feature=feature,
                entry_point=entry_point,
            )
            self._contracts[identifier] = record

    def list_by_gherkin(self, step_text: str) -> list[ContractRecord]:
        """Find all contracts derived from a given Gherkin step."""
        return [r for r in self._contracts.values() if r.from_gherkin == step_text]

    def list_by_entry_point(
        self, entry_point: str, kind: ContractKind | None = None
    ) -> list[ContractRecord]:
        """Find every contract declared for a given entry point.

        This is the authoritative answer to "which contracts apply to this
        operation?" — it does not rely on naming conventions or on a test
        author remembering to enumerate them by hand.
        """
        return [
            r
            for r in self._contracts.values()
            if r.entry_point == entry_point and (kind is None or r.kind == kind)
        ]

    def preconditions_for(self, entry_point: str) -> list[ContractRecord]:
        return self.list_by_entry_point(entry_point, ContractKind.PRECONDITION)

    def postconditions_for(self, entry_point: str) -> list[ContractRecord]:
        return self.list_by_entry_point(entry_point, ContractKind.POSTCONDITION)

    def invariants_for(self, entry_point: str) -> list[ContractRecord]:
        return self.list_by_entry_point(entry_point, ContractKind.INVARIANT)

    def register_args_type(self, entry_point: str, args_type: type) -> None:
        """Record the canonical Args subtype for an entry point.

        Every precondition/postcondition registered under the same
        entry_point must agree on this type.  Raises ValueError the
        moment a contract disagrees — this is a registration-time
        well-formedness check, not something discovered later at call
        time via an AttributeError on the wrong field.
        """
        with self._lock:
            existing = self._entry_point_args_type.get(entry_point)
            if existing is not None and existing is not args_type:
                raise ValueError(
                    f"entry_point {entry_point!r} already uses "
                    f"{existing.__qualname__} as its canonical Args type; "
                    f"got {args_type.__qualname__} instead"
                )
            self._entry_point_args_type[entry_point] = args_type

    def register_result_type(self, entry_point: str, result_type: type) -> None:
        """Record the canonical Result subtype for an entry point.

        Same consistency guarantee as register_args_type, applied to the
        `result` parameter of every postcondition.
        """
        with self._lock:
            existing = self._entry_point_result_type.get(entry_point)
            if existing is not None and existing is not result_type:
                raise ValueError(
                    f"entry_point {entry_point!r} already uses "
                    f"{existing.__qualname__} as its canonical Result type; "
                    f"got {result_type.__qualname__} instead"
                )
            self._entry_point_result_type[entry_point] = result_type

    def args_type_for(self, entry_point: str) -> type | None:
        return self._entry_point_args_type.get(entry_point)

    def result_type_for(self, entry_point: str) -> type | None:
        return self._entry_point_result_type.get(entry_point)

    def get(self, identifier: str) -> ContractRecord | None:
        return self._contracts.get(identifier)

    def list_all(self) -> list[ContractRecord]:
        return list(self._contracts.values())

    def list_by_kind(self, kind: ContractKind) -> list[ContractRecord]:
        return [r for r in self._contracts.values() if r.kind == kind]

    def list_by_module(self, module: str) -> list[ContractRecord]:
        return [r for r in self._contracts.values() if r.module == module]

    def clear(self) -> None:
        with self._lock:
            self._contracts.clear()
            self._entry_point_args_type.clear()
            self._entry_point_result_type.clear()

    def __len__(self) -> int:
        return len(self._contracts)

    def __contains__(self, identifier: str) -> bool:
        return identifier in self._contracts


_registry: ContractRegistry | None = None
_registry_lock = threading.Lock()


def get_registry() -> ContractRegistry:
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = ContractRegistry()
    return _registry
