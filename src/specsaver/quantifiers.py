from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")


def forall(domain: Any, predicate: Callable[[Any], bool]) -> bool:
    """Universal quantification over a domain.

    domain may be a concrete collection or an abstract generator.
    """
    return all(predicate(x) for x in domain)


def exists(domain: Any, predicate: Callable[[Any], bool]) -> bool:
    """Existential quantification over a domain.

    domain may be a concrete collection or an abstract generator.
    """
    return any(predicate(x) for x in domain)
