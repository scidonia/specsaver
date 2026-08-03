# Implementation Lowering: Python Services → SnakeletExn Programs

## Why This Matters

The current verification pipeline proves the *contract* is internally sound
(pre/post consistency, frame soundness, invariant preservation — 23/23
obligations).  It does not prove that the Python *implementation* satisfies
the contract.  The connection is established empirically by the scenario
runner, which exercises concrete Gherkin rows against real SQLite.

To close the loop, we need to **lower the implementation into SnakeletExn**
and prove refinement: the lowered program must satisfy the FunSpecS
specification that was generated from the contract.

## Current State

| Layer | Status |
|---|---|
| Contract lowering (Python predicates → SnakeletExn FunSpecS) | **Done** — 23/23 obligations proved |
| Implementation lowering (Python service → SnakeletExn program) | **Future** — specified below |
| Refinement proof (lowered impl ⊨ contract spec) | **Future** — depends on impl lowering |

## What Gets Lowered

The Python service function is a straight-line transactional body wrapped in
SQLAlchemy's `engine.begin()`:

```python
def reserve(self, engine, sku, order_id, quantity):
    with engine.begin() as conn:          # transaction boundary
        row = conn.execute(               # SQL: SELECT on_hand, reserved
            text("SELECT on_hand, reserved FROM products WHERE sku = :sku"),
            {"sku": sku}
        ).fetchone()

        if row is None:                   # control flow: branch
            raise ProductNotFoundError(sku, order_id, quantity, ...)

        on_hand, reserved = row
        available = on_hand - reserved    # pure computation

        if available < quantity:          # control flow: branch
            raise InsufficientStockError(sku, quantity, available)

        conn.execute(                     # SQL: UPDATE products SET reserved
            text("UPDATE products SET reserved = reserved + :qty"
                 " WHERE sku = :sku"),
            {"qty": quantity, "sku": sku},
        )

    return ReservationReceipt(...)         # return value
```

The lowerer must translate each construct into SnakeletExn:

| Python construct | SnakeletExn target |
|---|---|
| `engine.begin()` | `STry` / `SCommit` / `SRollback` — transaction framing |
| `conn.execute(text("SELECT ..."), params)` | `HeadCallSpecS "conn.execute"` — adorned call via FunSpecS |
| `.fetchone()` | Unwraps the `LitList` result from the execute spec |
| `row is None` | `SIf` with `is LitUnit` |
| `raise E(args)` | `SRaise (Val (SExn "InsufficientStockError" payload_list))` |
| `on_hand - reserved` | `SBinOp Minus` |
| `conn.execute(text("UPDATE ..."), params)` | `HeadCallSpecS "conn.execute_update"` |
| `return ReservationReceipt(...)` | `SVal (SDict [...])` |
| `with engine.begin() as conn:` | `STry` — commit on normal exit, rollback on `SRaise` |

## The Adornment Registry

SQLAlchemy calls are intercepted via the theory's adornment registry
(`specsaver.theory.sql`).  The `translate_sql` function maps each SQL string
to a theory action model (`Select`, `Insert`, `Update`).  The lowerer uses
the same translation:

1. Parse the `text(...)` argument via `sqlglot` → theory action
2. Look up the adorned callable in the registry → `CallRule`
3. Emit a `HeadCallSpecS` whose pre/post match the theory's operational
   semantics

This is the same mechanism the `_lower_call` specification from
`Exception-Effect-Lowering-Spec.md` describes.

## Exception Lowering

Python's `raise E(args)` carries structured payload fields (e.g.,
`exc.available`, `exc.sku`).  These must be preserved in the lowered form
because the contract's exception `ensures` clauses reference them (e.g.,
`extends_by_one(old.failure_log, new.failure_log, λf: f.available ==
exc.available)`).

The lowering follows `Exception-Effect-Lowering-Spec.md`:

1. `raise InsufficientStockError(sku, quantity, available)` lowers to:
   ```
   SRaise (Val (LitExn "InsufficientStockError" (LitTuple
     [LitInt available; LitString sku; LitString order_id; LitInt quantity])))
   ```

2. The handler in the `STry` block pattern-matches on the exception label
   and destructures the payload — though in the current service pattern,
   exceptions are uncaught (they propagate to the `engine.begin()`
   transaction boundary, which rolls back).

## Refinement Proof

Once the implementation is lowered to a SnakeletExn program `P`, we prove:

```
⊢ WPE P {{ post }}
  where post matches the FunSpecS gen_post from the contract lowering
```

The WP calculus guarantees that if `P` executes to a result `r` in state
`σ'`, then `gen_post(σ, args, r, σ')` holds.  This is the refinement
property: the lowered implementation satisfies the contract specification.

The proof uses the standard Iris WP tactics (`wp_bind`, `wp_load`,
`wp_store`, `wp_call`, `wp_raise`, `wp_try`) plus the lemma `gen_table_total`
that proves the `FunSpecS` entries are total.

## Phased Plan

### Phase 1: Straight-line service lowering (no exceptions)

Lower a service with no branches and no exceptions (e.g., `restock`):

```python
def restock(self, engine, sku, quantity):
    with engine.begin() as conn:
        row = conn.execute(text("SELECT on_hand FROM products WHERE sku = :sku"), {"sku": sku}).fetchone()
        if row is None: raise ProductNotFoundError(sku, "", quantity, ...)
        conn.execute(text("UPDATE products SET on_hand = on_hand + :qty WHERE sku = :sku"), {"qty": quantity, "sku": sku})
    return RestockReceipt(receipt_id=..., sku=sku, quantity=quantity)
```

Prove that the lowered program satisfies `restock_contract`'s FunSpecS.

### Phase 2: Exception handling

Add `raise`/`STry` lowering for services with exception paths
(`reserve`, `release`, `transfer`).  Prove that exception arms
correctly produce `RExn` results matching the exception spec.

### Phase 3: Multi-delta transaction services

Handle services with multiple updates in one transaction (`transfer`:
two `UPDATE` statements).  Prove the combined transaction against
the multi-delta FunSpecS.

### Phase 4: Adorned call fidelity

Prove that `HeadCallSpecS` for each SQLAlchemy call matches the
theory's operational semantics (the differential validation already
establishes this empirically for the theory; the proof fills the
gap).

## Trust Model After Implementation Lowering

Once implementation lowering is complete, the trust model is:

| Component | Status |
|---|---|
| Rocq kernel | Trusted |
| SnakeletExn (language + WP calculus) | Hand-written, must correctly model Python semantics |
| SpecPrelude (dict helpers) | Proved in Coq |
| FunSpecS kernel | Proved in Coq (total specs) |
| Contract lowering (Python predicates → FunSpecS) | Trusted code (not proved correct) |
| **Implementation lowering (Python service → SnakeletExn)** | **Trusted code (not proved correct)** |
| Refinement proof (lowered impl ⊨ spec) | Machine-proved in Coq |
| Theory stub fidelity (stub vs real SQLAlchemy) | Tested empirically |

The critical trusted components are:
- The SnakeletExn language accurately models Python semantics
- The emitter correctly translates Python AST to SnakeletExn
- The emitter correctly translates the contract to FunSpecS

These are all amenable to differential testing — the same approach we use
for the SQL theory.

## Connection to Existing Machinery

| Existing | How it's reused |
|---|---|
| `specsaver.theory.sql` — action model + stub | Provides `CallRule` registry, `translate_sql` for SQL → action |
| `specsaver.lower.introspect` — shape extraction | Reused for implementation shape (branches, calls, returns) |
| `specsaver.lower.emit` — Coq generation | Extended to emit SnakeletExn programs, not just predicates |
| `coq/SnakeletExnLang.v` — language | Target for lowering |
| `coq/SnakeletExnWp.v` — WP calculus | Used for refinement proofs |
| `coq/ReserveLowering.v` — hand-written example | Template for automated lowering |
