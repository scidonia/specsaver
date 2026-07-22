"""Generic domain conformance suite — one file tests every domain.

Any :class:`~specsaver.domain.SqlDomain` that is imported before this
file runs (via a module-level import of the domain package) is
auto-discovered and every Examples row of every feature is exercised.
"""

from __future__ import annotations

from typing import Any

import pytest

from specsaver.domain import SqlDomain, registered_domains


def _import_all_domains() -> None:
    """Import every registered domain package.

    Called at collection time so the registry is populated.
    Add new domain packages here.
    """
    import examples.bank_transfer  # noqa: F401
    import examples.inventory  # noqa: F401
    import examples.invitations  # noqa: F401


_import_all_domains()

_domains = registered_domains()

_ALL_CASES: list[list] = []
for pkg, domain in _domains.items():
    runners = domain.runners()
    for op in domain.operations:
        runner = runners[op.feature_file]
        domain_cases = domain.all_cases
        for feature, _op, row in domain_cases:
            if feature == op.feature_file:
                _ALL_CASES.append([pkg, feature, row, runner])

_IDS = [
    f"{case[0].rsplit('.', 1)[-1]}:{case[1]}:{case[2].get('outcome', '?')}"
    for case in _ALL_CASES
]


# ---------------------------------------------------------------------------
# Per-domain metadata checks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("pkg,domain", [  # noqa: PT006
    (p, d) for p, d in _domains.items()
])
def test_domain_loads(pkg: str, domain: SqlDomain) -> None:
    assert domain.name
    assert len(domain.operations) > 0
    runners = domain.runners()
    assert len(runners) == len(domain.operations)


# ---------------------------------------------------------------------------
# Every row of every feature of every domain
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "pkg, feature, row, runner",
    _ALL_CASES,
    ids=_IDS,
)
def test_run_scenario_generic(
    pkg: str, feature: str, row: dict[str, str], runner: Any,
) -> None:
    passed, message = runner.run(row)
    assert passed, f"[{pkg}/{feature}] failed: {message}"
