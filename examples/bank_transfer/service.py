"""Transfer service — the implementation.

This is the code under verification.  It has no knowledge of the contract
language itself, but it uses the domain types defined by the contracts,
including the canonical `TransferArgs` input type, so that
`specsaver.verify.run_entry_point` can call it uniformly as
`impl(state, args) -> result`.  The contracts in `contracts.py` are the
external specification against which this implementation is verified.
"""

from examples.bank_transfer.contracts import (
    AccountState,
    TransferArgs,
    TransferReceipt,
)


class TransferService:
    """Implementation of funds transfer — unaware of contracts."""

    _counter: int = 0

    @classmethod
    def _next_id(cls) -> str:
        cls._counter += 1
        return f"tx-{cls._counter:06d}"

    def transfer(self, state: AccountState, args: TransferArgs) -> TransferReceipt:
        source_id, target_id, amount = (
            args.source_id,
            args.target_id,
            args.amount,
        )

        if amount <= 0:
            return TransferReceipt(
                transaction_id=self._next_id(),
                source_id=source_id,
                target_id=target_id,
                amount=amount,
                success=False,
            )

        source = state.accounts.get(source_id)
        target = state.accounts.get(target_id)

        if source is None or target is None:
            return TransferReceipt(
                transaction_id=self._next_id(),
                source_id=source_id,
                target_id=target_id,
                amount=amount,
                success=False,
            )

        if source.currency != target.currency:
            return TransferReceipt(
                transaction_id=self._next_id(),
                source_id=source_id,
                target_id=target_id,
                amount=amount,
                success=False,
            )

        if source.balance < amount:
            return TransferReceipt(
                transaction_id=self._next_id(),
                source_id=source_id,
                target_id=target_id,
                amount=amount,
                success=False,
            )

        source.balance -= amount
        target.balance += amount

        return TransferReceipt(
            transaction_id=self._next_id(),
            source_id=source_id,
            target_id=target_id,
            amount=amount,
            success=True,
        )
