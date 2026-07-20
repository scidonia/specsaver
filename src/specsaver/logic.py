"""Logical operators for contract expressions.

These are contract-level primitives that make conditional structure
explicit in a single expression, replacing multi-line if/return guards.
"""

from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


def implies(p: bool, q: bool) -> bool:
    """Logical implication: ``p → q`` ≡ ``¬p ∨ q``."""
    return not p or q


def extends_by_one(
    old: tuple[T, ...], new: tuple[T, ...], predicate: Callable[[T], bool],
) -> bool:
    """True iff *new* is *old* with exactly one element appended,
    and the appended element satisfies *predicate*."""
    return (
        len(new) == len(old) + 1
        and new[:-1] == old
        and predicate(new[-1])
    )
