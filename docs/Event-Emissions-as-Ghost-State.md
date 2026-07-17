# Event emissions in the specification state

## Thesis

Events are not a first-class contract element. They are observations projected
into the specification state and verified through the same postcondition
machinery as database rows and derived values. The single source of semantic
truth is the postcondition over `SpecState`.

## The interpretation function

The projection `snapshot` is an interpretation from the concrete execution
environment to the abstract specification state:

```
snapshot : ConcreteExecution → SpecState
```

`ConcreteExecution` bundles the database connection, the event log, and any
other concrete resource the implementation touches. `SpecState` is the
immutable abstract state the contracts reason about. The same `snapshot` is
called before and after execution — this is the symmetry requirement that
makes pre/post reasoning sound.

```
   concrete world                    snapshot            abstract state
   ──────────────                    ────────            ──────────────
   SQLite DB     ──────────────┬──→  snapshot(ctx)   →  observed.accounts
   EventLog      ──────────────┘                     →  observed.audit_log
                                                        observed.notif_log
                                                        derived.total_balance
                                                        ghost.initial_total
```

All observations — database rows, log entries, file contents — populate the
`observed` component of `SpecState`. `derived` holds pure functions of
observed data (e.g. `total_balance = sum(...)`). `ghost` is reserved for
specification-only artefacts with no concrete representation (e.g. the
initial total balance used to prove conservation). Event logs have a
concrete representation (the logging module, a message queue, stdout) and
therefore belong in `observed`.

## Provenance decomposition

The contract author sees the provenance split only when defining the
projection. At the logical level — the rendered contract — the distinction
between `observed`, `derived`, and `ghost` is elided. The renderer strips
these prefixes:

```
state.observed.accounts     →  state.accounts
state.derived.total_balance →  state.total_balance
state.ghost.initial_total   →  ghost.initial_total
```

The contract says *what* must be true about the abstract state. How that
state was assembled — from a database, from a log, from pure computation —
is the projection's responsibility.

## Events as observed state

Event logs are structurally identical to database tables: both are concrete
resources written by the implementation and read by the projection. An
event emission becomes an `append` to an observed log:

```python
@dataclass(frozen=True)
class TransferObserved:
    accounts: Mapping[str, Account]
    audit_log: list[TransferCompleted]       # concrete event log
    notif_log: list[FundsReceived]           # concrete event log
```

Postconditions constrain these logs just like they constrain account
balances:

```python
ensures=[
    # State transition
    lambda old_s, args, result, new_s: (
        new_s.observed.accounts[args.source_id].balance
        == old_s.observed.accounts[args.source_id].balance - args.amount
    ),
    # Emission — same mechanism
    lambda old_s, args, result, new_s: (
        len(new_s.observed.audit_log)
        == len(old_s.observed.audit_log) + 1
        and new_s.observed.audit_log[-1].transaction_id
            == result.transaction_id
    ),
]
```

On exception exit:

```python
ExcExit(
    ensures=[
        lambda state, args, exc, after_s: (
            len(after_s.observed.audit_log)
            == len(state.observed.audit_log)    # no events emitted
        ),
    ],
)
```

No separate `emits` field. No ``channel`` abstraction. Events are just data.

## Channels

The previous design used named channels (`audit`, `notification`) as routing
labels. The AI correctly observed that channels are an operational concern,
not a logical one. The contract should not specify *where* an event goes —
only *what* events must be present in the observed state. Channel routing is
handled by the implementation and verified by the projection: the projection
reads the concrete event log and populates the correct observed fields.

## The render surface

The renderer can optionally display a summary of event-related postconditions
as syntactic sugar — a derived `emits:` section that elaborates from the
ensures predicates. But this is documentation, not verification. The
underlying semantics remain ordinary postconditions over `SpecState`.

## From testing to proof

The architecture supports a direct path to formal proof because testing and
proof evaluate the same predicates over the same abstract state:

| Component | Testing | Proof |
|-----------|---------|-------|
| `snapshot` | Runs against concrete DB + EventLog | Axiom: `snapshot(ctx) = S` |
| `requires` | Checked before execution | Precondition in the proof calculus |
| `ensures` | Checked after execution | Postcondition in the proof calculus |
| `invariant` | Checked before and after | Inductive invariant |
| Exception `ensures` | Checked on exception exit | Proof case for exceptional return |

The `snapshot` function is the semantic bridge that must be justified — the
correctness of the projection is the key proof obligation linking the
concrete implementation to the abstract specification.

## Summary

- **Event logs are observed state**, not ghost state. They have concrete
  representation.
- **The projection is the interpretation function** from concrete to
  abstract. It reads everything — database, logs, files — and produces a
  complete `SpecState`.
- **Postconditions verify everything**, including event emissions. No
  separate verification path.
- **The provenance split** (observed/derived/ghost) is the projection's
  implementation detail. The contract surface is provenance-agnostic.
- **Channels are operational**, not logical. Routing happens in the
  implementation, not the contract.
