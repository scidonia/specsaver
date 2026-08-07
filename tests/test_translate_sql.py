"""BDD step definitions for translate_sql."""

from __future__ import annotations

from pathlib import Path

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from examples.translate.service import TranslateService
from examples.translate.types import TranslateArgs
from specsaver.theory.sql import Select, Insert, Update, UnsupportedStatementError

_FEATURE_FILE = (
    Path(__file__).parent.parent / "tests" / "theory" / "translate_sql.feature"
)

scenarios(str(_FEATURE_FILE))


@pytest.fixture
def ctx():
    return {}


@given("the theory SQL translator")
def given_translator(ctx):
    ctx["svc"] = TranslateService()


@when(parsers.parse("{query} with params {params} is translated"))
def when_translate(query, params, ctx):
    _execute(query, params, ctx)


@when(parsers.parse("{query} is translated"))
def when_translate_no_params(query, ctx):
    _execute(query, "", ctx)


def _parse_params(params_str: str) -> tuple:
    """Parse a params string like ('S1',) or (30, 'S1') into a tuple."""
    inner = params_str.strip().strip("()")
    if not inner:
        return ()
    result = []
    for p in inner.split(","):
        p = p.strip().strip('"').strip("'")
        if not p:
            continue
        try:
            result.append(int(p))
        except ValueError:
            result.append(p)
    return tuple(result)


def _execute(query: str, params_str: str, ctx):
    query = query.strip().strip('"')
    params = _parse_params(params_str)

    svc = ctx["svc"]
    args = TranslateArgs(sql=query, params=params)
    try:
        result = svc.translate(args)
        ctx["result"] = result.stmt
        ctx["exception"] = None
    except UnsupportedStatementError as exc:
        ctx["result"] = None
        ctx["exception"] = exc

    ctx["sql"] = query
    ctx["params"] = params


@then(parsers.parse("the result is a Select on {table} with columns {cols}"))
def then_select_result(table, cols, ctx):
    assert ctx["exception"] is None, f"Unexpected exception: {ctx['exception']}"
    assert ctx["result"] is not None, "Expected a result"
    assert isinstance(ctx["result"], Select), f"Expected Select, got {type(ctx['result']).__name__}"
    assert ctx["result"].table == table.strip(), f"table: {ctx['result'].table} != {table}"
    if cols.strip() and cols.strip() != "*":
        expected = tuple(c.strip() for c in cols.split(",") if c.strip())
        assert ctx["result"].columns == expected, f"columns: {ctx['result'].columns} != {expected}"


@then(parsers.parse("the result is an Insert on {table}"))
def then_insert_result(table, ctx):
    assert ctx["exception"] is None, f"Unexpected exception: {ctx['exception']}"
    assert ctx["result"] is not None, "Expected a result"
    assert isinstance(ctx["result"], Insert), f"Expected Insert, got {type(ctx['result']).__name__}"
    assert ctx["result"].table == table.strip()


@then(parsers.parse("the result is an Update on {table}"))
def then_update_result(table, ctx):
    assert ctx["exception"] is None, f"Unexpected exception: {ctx['exception']}"
    assert ctx["result"] is not None, "Expected a result"
    assert isinstance(ctx["result"], Update), f"Expected Update, got {type(ctx['result']).__name__}"
    assert ctx["result"].table == table.strip()


@then("the translation is rejected")
def then_rejected(ctx):
    assert ctx["exception"] is not None, f"Expected an exception, got result: {ctx['result']}"
    assert isinstance(ctx["exception"], UnsupportedStatementError), \
        f"Expected UnsupportedStatementError, got {type(ctx['exception']).__name__}: {ctx['exception']}"
