"""Contract decorators — the single source of semantic truth.

Every contract proposition carries exactly one decorator that classifies it.
The contract may declare:
  - its Gherkin origin via `from_gherkin`, and the feature file via `feature`
  - the entry point it belongs to via `entry_point`

`entry_point` is what makes contracts *discoverable as a set*: every
precondition/postcondition tagged with the same `entry_point` name is
part of that operation's authoritative contract.  Tests should query the
registry for "all preconditions/postconditions of entry point X" rather
than hand-listing individual contract functions — see
`specsaver.verify.run_entry_point`.

For this to work, every precondition for a given entry point must share
the canonical signature `Pre(state, args) -> bool`, and every
postcondition must share `Post(old_state, args, result, new_state) ->
bool` — exactly as specified in the architecture document.  `args` is a
single structured input object (an `Args` subclass, see `specsaver.args`),
not a scattered argument list, and `result` is a single structured output
object (a `Result` subclass).

Registration enforces this: when `entry_point` is set, the `args`
parameter of a precondition/postcondition (and the `result` parameter of
a postcondition) must be annotated with an `Args`/`Result` subclass, and
every contract sharing the same entry_point must agree on exactly which
subclass — a mismatch raises immediately at registration time, not later
as a call-time AttributeError on the wrong field.

Usage:
    @dataclass(frozen=True)
    class TransferArgs(Args):
        source_id: str
        target_id: str
        amount: int

    @precondition(
        entry_point="transfer",
        from_gherkin="Given an account with balance",
    )
    def transfer_pre_valid_amount(state: AccountState, args: TransferArgs) -> bool:
        return args.amount > 0

    @postcondition(
        entry_point="transfer",
        from_gherkin="Then the total balance is unchanged",
        feature="transfer.feature",
    )
    def transfer_post_total_preserved(old_s, args, result, new_s) -> bool:
        ...
"""

from __future__ import annotations

import inspect
import typing
from collections.abc import Callable
from typing import Any, TypeVar

from specsaver.args import Args, Result
from specsaver.registry import get_registry
from specsaver.types import ContractKind

F = TypeVar("F", bound=Callable[..., Any])


def _extract_param_type(f: Callable[..., Any], index: int, role: str) -> type:
    """Get the resolved type annotation of the parameter at `index`.

    Uses typing.get_type_hints rather than raw inspect.signature
    annotations so that modules using `from __future__ import annotations`
    (postponed evaluation, PEP 563) still resolve to real classes instead
    of unevaluated strings.
    """
    sig = inspect.signature(f)
    params = list(sig.parameters.keys())
    if len(params) <= index:
        raise TypeError(
            f"{f.__qualname__}: contracts with entry_point set must take a "
            f"{role!r} parameter at position {index}"
        )
    param_name = params[index]
    hints = typing.get_type_hints(f)
    annotation = hints.get(param_name)
    if annotation is None:
        raise TypeError(
            f"{f.__qualname__}: parameter {param_name!r} ({role}) must be "
            f"type-annotated"
        )
    return annotation


def _check_subclass(
    annotation: Any, base: type, f: Callable[..., Any], role: str
) -> None:
    if isinstance(annotation, type) and issubclass(annotation, base):
        return
    args = typing.get_args(annotation)
    if args:
        for arg in args:
            if isinstance(arg, type) and issubclass(arg, base):
                return
        raise TypeError(
            f"{f.__qualname__}: no member of the {role} union "
            f"({annotation!r}) is a {base.__name__} subclass"
        )
    raise TypeError(
        f"{f.__qualname__}: the {role} parameter must be annotated with "
        f"a {base.__name__} subclass, got {annotation!r}"
    )


def _enforce_canonical_signature(
    kind: ContractKind, f: Callable[..., Any], entry_point: str
) -> None:
    """Validate and register the canonical Args/Result types for entry_point."""
    if kind is ContractKind.PRECONDITION:
        args_type = _extract_param_type(f, 1, "args")
        _check_subclass(args_type, Args, f, "args")
        get_registry().register_args_type(entry_point, args_type)
    elif kind is ContractKind.POSTCONDITION:
        args_type = _extract_param_type(f, 1, "args")
        _check_subclass(args_type, Args, f, "args")
        get_registry().register_args_type(entry_point, args_type)

        result_type = _extract_param_type(f, 2, "result")
        _check_subclass(result_type, Result, f, "result")
        get_registry().register_result_type(entry_point, result_type)


def _register(
    kind: ContractKind,
    f: F,
    *,
    from_gherkin: str | None = None,
    feature: str | None = None,
    entry_point: str | None = None,
) -> F:
    qualname = f.__qualname__
    module = inspect.getmodule(f)
    module_name = module.__name__ if module else "__unknown__"

    if entry_point is not None:
        _enforce_canonical_signature(kind, f, entry_point)

    f._specsaver_kind = kind
    f._specsaver_module = module_name
    f._specsaver_qualname = qualname
    f._specsaver_from_gherkin = from_gherkin
    f._specsaver_feature = feature
    f._specsaver_entry_point = entry_point

    get_registry().register(
        identifier=f"{module_name}.{kind.name.lower()}.{qualname}",
        kind=kind,
        func=f,
        module=module_name,
        qualname=qualname,
        from_gherkin=from_gherkin,
        feature=feature,
        entry_point=entry_point,
    )
    return f


def _make_decorator(kind: ContractKind):
    """Factory for decorators accepting `from_gherkin`/`feature`/`entry_point`."""

    def dec(
        f=None,
        /,
        *,
        from_gherkin=None,
        feature=None,
        entry_point=None,
    ):
        if f is not None:
            return _register(
                kind,
                f,
                from_gherkin=from_gherkin,
                feature=feature,
                entry_point=entry_point,
            )
        return lambda f: _register(
            kind,
            f,
            from_gherkin=from_gherkin,
            feature=feature,
            entry_point=entry_point,
        )

    dec.__name__ = kind.name.lower()
    return dec


precondition = _make_decorator(ContractKind.PRECONDITION)
postcondition = _make_decorator(ContractKind.POSTCONDITION)
invariant = _make_decorator(ContractKind.INVARIANT)
predicate = _make_decorator(ContractKind.PREDICATE)
function = _make_decorator(ContractKind.FUNCTION)
writes = _make_decorator(ContractKind.WRITES)
reads = _make_decorator(ContractKind.READS)
effect = _make_decorator(ContractKind.EFFECT)
exceptional = _make_decorator(ContractKind.EXCEPTIONAL)
ghost_update = _make_decorator(ContractKind.GHOST_UPDATE)


def _exceptional_dec(
    f=None,
    /,
    *,
    exc_type: Any | None = None,
    from_gherkin=None,
    feature=None,
    entry_point=None,
):
    """Decorator for exception contracts — associates an exception type
    with the condition under which it is raised.

    ``exc_type`` is stored as ``_specsaver_exc_type`` on the function
    so the runner can match caught exceptions to their contracts.
    """
    kind = ContractKind.EXCEPTIONAL

    def wrap(func):
        if exc_type is not None:
            name = exc_type.code if hasattr(exc_type, "code") else exc_type.__qualname__
            func._specsaver_exc_type = name
        return _register(
            kind,
            func,
            from_gherkin=from_gherkin,
            feature=feature,
            entry_point=entry_point,
        )

    if f is not None:
        return wrap(f)
    return wrap


exceptional = _exceptional_dec


def ghost(cls: type) -> type:
    """Mark a class as ghost state — specification-only, not in the implementation."""
    return _register(ContractKind.GHOST, cls)


def measure(measure_fn: Callable[..., int]) -> Callable[[F], F]:
    """Attach an explicit termination measure to a recursive function."""

    def decorator(f: F) -> F:
        f._specsaver_measure = measure_fn
        return _register(ContractKind.MEASURE, f)

    return decorator
