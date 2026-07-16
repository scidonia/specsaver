"""Logical operators for contract expressions.

These are contract-level primitives that make conditional structure
explicit in a single expression, replacing multi-line if/return guards.
"""


def implies(p: bool, q: bool) -> bool:
    """Logical implication: ``p → q`` ≡ ``¬p ∨ q``."""
    return not p or q
