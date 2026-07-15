"""Binding — invoke real implementation callables from a canonical Args object.

Contracts always reason about a single Args/Result pair (see specsaver.args)
— that uniformity is what makes an entry point's contract set discoverable
regardless of how many fields the operation takes.  The implementation
under verification, however, may have an arbitrary native Python
signature: positional-only parameters, positional-or-keyword parameters,
*args, keyword-only parameters, **kwargs, and default values.  `bind_call`
adapts a single Args instance to whatever real call shape `impl` requires,
supporting the full matrix of Python parameter kinds.
"""

from __future__ import annotations

import dataclasses
import inspect
from collections.abc import Callable
from typing import Any

from specsaver.args import Args

_POSITIONAL_ONLY = inspect.Parameter.POSITIONAL_ONLY
_POSITIONAL_OR_KEYWORD = inspect.Parameter.POSITIONAL_OR_KEYWORD
_VAR_POSITIONAL = inspect.Parameter.VAR_POSITIONAL
_VAR_KEYWORD = inspect.Parameter.VAR_KEYWORD
_EMPTY = inspect.Parameter.empty


def bind_call(
    impl: Callable[..., Any],
    *leading: Any,
    args: Args,
    spread: bool = False,
    varargs_field: str | None = None,
    varkwargs_field: str | None = None,
) -> Any:
    """Call `impl` given `leading` positional args followed by `args`.

    spread=False (default): `impl` is called as `impl(*leading, args)` —
    the whole Args object is passed as a single trailing positional
    parameter.  This is the common case where the implementation was
    written (or adapted) to take the canonical Args type directly, e.g.
    `def transfer(self, state, args: TransferArgs): ...`.

    spread=True: `impl` may have an arbitrary native signature.  Fields of
    `args` are matched against `impl`'s real parameters by name:
      - POSITIONAL_ONLY parameters are always passed positionally, in
        declared order.
      - POSITIONAL_OR_KEYWORD parameters are normally passed as a keyword
        — *except* when the signature also has a `*args` (VAR_POSITIONAL)
        parameter later on, in which case they must be passed positionally
        too.  Python fills positional slots strictly left to right; if a
        POSITIONAL_OR_KEYWORD parameter were passed by keyword while later
        values were also appended positionally for `*args`, those values
        would collide with (or silently shift into) that parameter's own
        positional slot.  Since Python's grammar guarantees every
        POSITIONAL_OR_KEYWORD parameter precedes any `*args` parameter,
        this is detected unambiguously from the signature alone.  For the
        same reason, such a parameter cannot be safely left at its default
        when a `*args` parameter follows and is being fed via
        `varargs_field` — doing so would leave an unfillable gap in the
        positional sequence, so this raises TypeError instead of guessing.
      - KEYWORD_ONLY parameters are always passed as a keyword; their
        defaults may be safely left alone regardless of surrounding *args,
        since keyword-only parameters are matched by name, not position.
      - VAR_POSITIONAL (*impl_args) is filled from the Args field named by
        `varargs_field`, if given (expects a tuple/list); otherwise empty.
      - VAR_KEYWORD (**impl_kwargs) is filled from the Args field named by
        `varkwargs_field` (expects a dict), and/or from any Args fields
        left over after matching named parameters.
      - a parameter with no matching Args field and no default raises
        TypeError (a well-formedness signal: the Args type does not cover
        something the implementation actually needs).
      - leftover Args fields with no matching parameter and no **kwargs to
        receive them also raise TypeError, rather than silently dropping
        data the implementation never sees.
    """
    if not spread:
        return impl(*leading, args)

    sig = inspect.signature(impl)
    data: dict[str, Any] = {
        f.name: getattr(args, f.name) for f in dataclasses.fields(args)
    }

    positional: list[Any] = list(leading)
    keywords: dict[str, Any] = {}

    params = list(sig.parameters.values())[len(leading) :]
    has_var_positional = any(p.kind is _VAR_POSITIONAL for p in params)
    has_var_keyword = any(p.kind is _VAR_KEYWORD for p in params)

    for p in params:
        if p.kind is _VAR_POSITIONAL:
            if varargs_field is not None:
                positional.extend(data.pop(varargs_field, ()))
            continue
        if p.kind is _VAR_KEYWORD:
            continue  # handled after all named parameters are consumed

        # A POSITIONAL_OR_KEYWORD parameter must be passed positionally
        # whenever a later *args parameter is also being fed positionally
        # — see the docstring for why.  POSITIONAL_ONLY is always
        # positional.  Everything else (KEYWORD_ONLY) is always a keyword.
        must_be_positional = p.kind is _POSITIONAL_ONLY or (
            p.kind is _POSITIONAL_OR_KEYWORD and has_var_positional
        )

        if p.name in data:
            value = data.pop(p.name)
            if must_be_positional:
                positional.append(value)
            else:
                keywords[p.name] = value
        elif p.default is _EMPTY:
            raise TypeError(
                f"{impl.__qualname__}: required parameter {p.name!r} has no "
                f"matching field on {type(args).__qualname__}"
            )
        elif must_be_positional:
            raise TypeError(
                f"{impl.__qualname__}: parameter {p.name!r} precedes a "
                f"*args parameter and must be supplied by "
                f"{type(args).__qualname__} — its default cannot be used "
                f"here, since skipping it would leave an unfillable gap "
                f"in the positional sequence"
            )

    if varkwargs_field is not None and varkwargs_field in data:
        keywords.update(data.pop(varkwargs_field))

    if data:
        if has_var_keyword:
            keywords.update(data)
        else:
            raise TypeError(
                f"{impl.__qualname__}: Args fields {sorted(data)} do not match "
                f"any parameter and it has no **kwargs to receive them"
            )

    return impl(*positional, **keywords)
