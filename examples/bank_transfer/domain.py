"""Bank Transfer — SqlDomain declaration (replaces most of projection.py)."""

from sqlalchemy import text

from examples.bank_transfer.contract import transfer_contract
from examples.bank_transfer.events import FundsReceived, TransferCompleted
from examples.bank_transfer.projection import (
    _FaultableTransferService,
    build_witness,
)
from examples.bank_transfer.types import (
    Account,
    TransferDerived,
    TransferGhost,
    TransferLimits,
    TransferObserved,
    TransferSpecState,
)
from specsaver.domain import (
    SqlDomain,
    SqlMaterializer,
    SqlOperation,
    SqlProjection,
    TableSpec,
)

_DDL = """
CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    balance INTEGER NOT NULL,
    currency TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS limits (
    key TEXT PRIMARY KEY,
    value INTEGER NOT NULL
);
"""

_TABLES = (
    TableSpec(
        name="accounts", key="id",
        columns=("id", "balance", "currency"),
        witness_key="accounts",
    ),
)


def _populate_limits(witness, conn):
    lim = witness.limits
    if lim is None:
        return
    if lim.per_transfer_max is not None:
        conn.execute(
            "INSERT INTO limits (key, value) VALUES (?, ?)",
            ("per_transfer_max", lim.per_transfer_max),
        )
    if lim.daily_remaining is not None:
        conn.execute(
            "INSERT INTO limits (key, value) VALUES (?, ?)",
            ("daily_remaining", lim.daily_remaining),
        )
    conn.commit()


def _extract_observed(context, table_dicts):
    accounts = {
        k: Account(id=k, balance=v["balance"], currency=v["currency"])
        for k, v in table_dicts["accounts"].items()
    }
    # Limits is a key/value lookup table — query it manually.
    with context.engine.connect() as conn:
        limit_rows = conn.execute(
            text("SELECT key, value FROM limits")
        ).fetchall()
    limits_dict = dict(limit_rows) if limit_rows else {}
    limits = TransferLimits(
        per_transfer_max=limits_dict.get("per_transfer_max"),
        daily_remaining=limits_dict.get("daily_remaining"),
    ) if limits_dict else None

    records = context.events._records
    return TransferObserved(
        accounts=accounts,
        limits=limits,
        audit_log=tuple(
            e for _, e in records if isinstance(e, TransferCompleted)
        ),
        notif_log=tuple(
            e for _, e in records if isinstance(e, FundsReceived)
        ),
    )


def _compute_derived(observed):
    return TransferDerived(
        total_balance=sum(a.balance for a in observed.accounts.values()),
    )


transfer_domain = SqlDomain(
    name="bank_transfer",
    package="examples.bank_transfer",
    materializer=SqlMaterializer(
        ddl=_DDL,
        tables=_TABLES,
        ghost_init=lambda w: TransferGhost(
            initial_total=sum(
                a.balance for a in w.accounts.values()
            )
        ),
        tempfile_prefix="specsaver_",
        populate_extra=_populate_limits,
    ),
    projection=SqlProjection(
        state_type=TransferSpecState,
        observed_type=TransferObserved,
        derived_type=TransferDerived,
        ghost_type=TransferGhost,
        tables=_TABLES,
        extract_observed=_extract_observed,
        compute_derived=_compute_derived,
    ),
    operations=(
        SqlOperation(
            transfer_contract, _FaultableTransferService(),
            build_witness, "transfer.feature",
        ),
    ),
)
