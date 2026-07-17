"""Safe division — contract."""

from examples.safe_div.projection import DivProjection
from examples.safe_div.service import SafeDivService
from examples.safe_div.types import DivArgs, DivisionError
from specsaver.contract_model import Contract, ExcExit

_projection = DivProjection()

divide_contract = Contract(
    SafeDivService.divide,
    args_type=DivArgs,
    feature="safe_div.feature",
    when='<dividend> is divided by <divisor>',
    observe=_projection.snapshot,
    requires=[
        lambda state, args: args.divisor != 0,
    ],
    ensures=[
        lambda old_s, args, result, new_s: (
            new_s.observed.quotient * args.divisor + new_s.observed.remainder
            == args.dividend
        ),
        lambda old_s, args, result, new_s: (
            new_s.observed.remainder >= 0
        ),
    ],
    exceptions=[
        ExcExit(
            raises=DivisionError,
            when=[
                lambda state, args: args.divisor == 0,
            ],
        ),
    ],
    invariants=[
        lambda state: state.derived.valid,
    ],
    derives={
        "valid": lambda state: (state.observed.quotient is None) == (state.observed.remainder is None),  # noqa: E501
    },
)
