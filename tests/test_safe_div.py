"""BDD step definitions for the safe_div example."""

from pathlib import Path

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from examples.safe_div.contract import divide_contract
from examples.safe_div.projection import build_witness
from examples.safe_div.service import SafeDivService
from examples.safe_div.types import DivObserved

_FEATURE_FILE = (
    Path(__file__).parent.parent / "examples" / "safe_div" / "safe_div.feature"
)

scenarios(str(_FEATURE_FILE))


@pytest.fixture
def ctx():
    return {}


@given(parsers.parse("a dividend {dividend:d}"))
def given_dividend(dividend, ctx):
    ctx["dividend"] = dividend


@given(parsers.parse("a divisor {divisor:d}"))
def given_divisor(divisor, ctx):
    ctx["divisor"] = divisor


@when(
    parsers.re(
        r'(?P<dividend>\S+) is divided by (?P<divisor>\S+)'
    )
)
def when_divide(dividend, divisor, ctx):
    row = {
        "dividend": str(ctx.get("dividend", dividend)),
        "divisor": str(ctx.get("divisor", divisor)),
    }
    witness = build_witness(row)
    args = witness.args

    before = divide_contract.observe(
        DivObserved(dividend=args.dividend, divisor=args.divisor)
    )

    pre_ok = all(p(before, args) for p in divide_contract.requires)
    if not pre_ok:
        ctx["rejected"] = True
        return

    ctx["rejected"] = False
    svc = SafeDivService()
    try:
        result = svc.divide(args.dividend, args.divisor)
    except Exception as exc:
        ctx["exception"] = exc
        after = DivObserved(
            dividend=args.dividend, divisor=args.divisor,
        )
        ctx["after"] = divide_contract.observe(after)
    else:
        ctx["result"] = result
        after_state = DivObserved(
            dividend=args.dividend, divisor=args.divisor,
            quotient=result.quotient, remainder=result.remainder,
        )
        ctx["after"] = divide_contract.observe(after_state)
    ctx["before"] = before
    ctx["args"] = args


@then("the quotient times divisor plus remainder equals the dividend")
def then_division_law(ctx):
    assert not ctx["rejected"]
    post = divide_contract.ensures[0]
    assert post(ctx["before"], ctx["args"], ctx["result"], ctx["after"])


@then("the remainder is non-negative")
def then_remainder_non_negative(ctx):
    assert not ctx["rejected"]
    post = divide_contract.ensures[1]
    assert post(ctx["before"], ctx["args"], ctx["result"], ctx["after"])


@then("the division is rejected")
def then_rejected(ctx):
    assert ctx["rejected"]
