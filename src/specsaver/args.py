"""Canonical Args/Result base classes for entry-point signatures.

Every precondition/postcondition sharing an `entry_point` must take the
*same* Args subtype as its structured input parameter, and every
postcondition must take the *same* Result subtype as its result parameter.
This turns "what does this operation accept/return?" into a single,
statically checkable answer — enforced at contract-registration time via
`specsaver.contract._register` — rather than a naming convention a test
author has to remember.

Usage:
    @dataclass(frozen=True)
    class TransferArgs(Args):
        source_id: str
        target_id: str
        amount: int

    @dataclass(frozen=True)
    class TransferReceipt(Result):
        transaction_id: str
        source_id: str
        target_id: str
        amount: int
        success: bool
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Args:
    """Base class for entry-point argument objects.

    Subclasses must also be frozen dataclasses.  Python enforces this
    automatically — a dataclass cannot mix frozen and non-frozen bases —
    which is exactly the immutability discipline contracts require: pure
    predicates must never be able to mutate the input they are asserting
    properties about.  No matter how many fields an entry point's Args
    subtype grows to have, the canonical contract signature never changes:
    `Pre(state, args) -> bool` / `Post(old_state, args, result, new_state)
    -> bool`.
    """


@dataclass(frozen=True)
class Result:
    """Base class for entry-point result objects.

    Subclasses must also be frozen dataclasses, for the same reason as
    Args: postconditions must not be able to mutate the value they are
    asserting properties about.
    """
