from typing import Any, TypeVar

from specsaver.types import Field

T = TypeVar("T")


def old(value: T) -> T:
    """Within a postcondition, evaluate *value* in the pre-state.

    At runtime this is a no-op — it returns value unchanged.
    The verifier desugars old(E) into a projection from the old-state argument.
    """
    return value


def unchanged(
    old_obj: Any,
    new_obj: Any,
    *,
    except_: frozenset[Field] | None = None,
) -> bool:
    """Assert that *old_obj* and *new_obj* are equal, modulo *except_* fields.

    At runtime this does a naive equality check.  The verifier uses field-path
    granularity to determine which parts may differ.
    """
    return old_obj == new_obj
