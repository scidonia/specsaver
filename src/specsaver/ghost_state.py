"""Ghost state — specification-only variables for the contract model.

Ghost variables carry state that exists in the specification but not in the
implementation.  They play the same role as ghost variables in Dafny.

Usage:
    @ghost
    class TransferLimits:
        daily_remaining: int
        monthly_remaining: int
        per_transfer_max: int
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class GhostState:
    """Container for ghost state attached to a component."""

    data: dict[str, Any]

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self.data[name]
        except KeyError:
            raise AttributeError(f"Ghost field {name!r} not found") from None

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "data":
            super().__setattr__(name, value)
        else:
            self.data[name] = value
