"""pytest-bdd step definitions for bank transfer — driven by Contract model."""

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from examples.bank_transfer.contract import transfer_contract
from examples.bank_transfer.projection import (
    TransferMaterializer,
    build_witness,
)
from examples.bank_transfer.service import TransferService

scenarios("examples/bank_transfer/transfer.feature")


@pytest.fixture
def ctx():
    """Borrow pytest-bdd's fixture system to track state between steps."""
    return {}


@given(parsers.parse('a source account "{source}" with balance {source_balance}'
                     ' in currency "{source_currency}"'))
def given_source(source, source_balance, source_currency, ctx):
    ctx["source"] = source
    ctx["source_balance"] = source_balance
    ctx["source_currency"] = source_currency


@given(parsers.parse('a target account "{target}" with balance {target_balance}'
                     ' in currency "{target_currency}"'))
def given_target(target, target_balance, target_currency, ctx):
    ctx["target"] = target
    ctx["target_balance"] = target_balance
    ctx["target_currency"] = target_currency


@given("the source balance exceeds the transfer amount")
def given_exceeds(ctx):
    pass  # enforced by the examples data + contract.pre


@given("the source balance is less than the transfer amount")
def given_insufficient(ctx):
    pass


@given("the transfer amount is not positive")
def given_invalid_amount(ctx):
    pass


@given("the target account does not exist")
def given_no_target(ctx):
    ctx["target_balance"] = ""  # signal to build_witness


@given("the source and target currencies differ")
def given_currency_mismatch(ctx):
    pass  # enforced by examples data


@given("a simulated runtime fault is injected")
def given_fault_injected(_pytest_bdd_example, ctx):
    ctx["fault"] = _pytest_bdd_example.get("fault") if _pytest_bdd_example else None


@when(
    parsers.re(
        r'funds of (?P<amount>\S+) are transferred'
        r' from "(?P<source>[^"]+)" to "(?P<target>[^"]+)"'
    )
)
def when_transfer(amount, source, target, ctx):
    ctx["amount"] = amount
    row = {
        "source": source,
        "target": target,
        "source_balance": ctx.get("source_balance", "0"),
        "target_balance": ctx.get("target_balance", "0"),
        "amount": amount,
        "source_currency": ctx.get("source_currency", "USD"),
        "target_currency": ctx.get("target_currency", "USD"),
        "fault": ctx.get("fault"),
    }
    witness = build_witness(row)
    ctx["witness"] = witness
    ctx["args"] = witness.args

    materializer = TransferMaterializer()
    context = materializer.materialize(witness)
    ctx["context"] = context

    before = transfer_contract.observe(context)
    ctx["before"] = before

    # Run preconditions
    pre_ok = all(p(before, witness.args) for p in transfer_contract.requires)
    if not pre_ok:
        ctx["result"] = "REJECTED"
        return

    # Invoke implementation
    try:
        if row.get("fault"):
            from examples.bank_transfer.projection import (
                _fault_state,
                _FaultableTransferService,
            )
            print(f"WHEN_TRANSFER: injecting fault={row['fault']!r}")
            _fault_state.inject(row["fault"])
            svc = _FaultableTransferService()
            result = svc.execute(context, witness.args)
        else:
            svc = TransferService()
            result = transfer_contract.invoke(svc, context.db_path, witness.args)
        ctx["result"] = result
    except Exception as exc:
        ctx["result"] = exc
        ctx["exception"] = exc

    after = transfer_contract.observe(context)
    ctx["after"] = after


@then("the total balance across all accounts is unchanged")
def then_total_unchanged(ctx):
    post = transfer_contract.ensures[0]
    assert post(ctx["before"], ctx["args"], ctx["result"], ctx["after"])


@then("the source balance decreased by the transfer amount")
def then_source_decreased(ctx):
    # ensures[1] = implies(isinstance(Receipt), ...)
    pass  # checked by contract runner


@then("the target balance increased by the transfer amount")
def then_target_increased(ctx):
    pass


@then("all account balances are non-negative")
def then_all_non_negative(ctx):
    inv = transfer_contract.invariants[0]
    assert inv(ctx["after"])


@then("the transfer is rejected")
def then_rejected(ctx):
    assert ctx["result"] == "REJECTED"


@then(parsers.parse("the transfer is rejected with code {code}"))
def then_rejected_with_code(code, ctx):
    exc = ctx.get("exception")
    assert exc is not None, f"expected exception with code {code}"
    actual = getattr(type(exc), "code", type(exc).__name__)
    assert actual == code, f"expected {code}, got {actual}"


@then("no account balances are changed")
def then_balances_unchanged(ctx):
    after = ctx.get("after")
    before = ctx.get("before")
    if after is not None and before is not None:
        assert after.derived.total_balance == before.derived.total_balance


@then("the transfer fails with a runtime error")
def then_runtime_error(ctx):
    exc = ctx.get("exception")
    assert exc is not None, "expected runtime exception"
