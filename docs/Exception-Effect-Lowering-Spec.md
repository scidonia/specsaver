# Exception and Effect Lowering — Build Specification

**Status:** Design — v0.1
**Scope:** What must be built to lower effectful, exception-raising
Python (inventory/bank_transfer-style services) onto Snakelet's
exception language, with adorned-library calls (SQL theory) as
`FunSpec` entries, feeding the obligation-dumping proof pipeline.

---

## 1. Where we actually are (correction to earlier claims)

Snakelet was designed with exceptions in mind, and more of the stack
exists than the phase notes suggested:

| Piece | State |
|---|---|
| `SnakeletExnLang.v` | Row-based exceptions (`LitExn label payload`), `Try e h` with handler application, raise unwinding through neutral contexts, uncaught-raise irreducible — **done** |
| `SnakeletExnWp.v` | `wp_exn` with `Result`-indexed postconditions (`RVal` / exceptional arm — native multi-postconditions), `wp_raise`, unwinding determinism lemmas — **done** |
| `SnakeletExnTactics.v` | staged tactics — **done** |
| `snakelet_ir.py` | `SRaise`, `STry` with `to_coq()`; `SDictGet` (DictModel) — **done** |
| `iris_lowerer.py` | `_lower_raise`: Python `raise E` → `SRaise(SLit exn)` — **label with unit payload** |
| `DictModel.v`, `ListPredicates.v` | dict-with-KeyError model, list predicates — **done, unwired** |
| `contract_ir.py` | `RaisesExpr` node exists |

The gaps are therefore **payload, dispatch, theory calls, and
exceptional postconditions** — not the exception model itself.

---

## 2. The four things to make

### A. Payload-carrying exceptions (lowering)

Python domain errors carry fields — `InsufficientStockError(sku,
order_id, quantity, available)` — and `ExcExit.ensures` predicates read
them (`exc.available = ...`).  The lowering must produce
`LitExn "InsufficientStockError" payload` where the payload is the
field tuple (or a dict via DictModel):

```
raise InsufficientStockError(sku, order_id, quantity, available)
  ⇒ SRaise(LitExn "InsufficientStockError"
                 (Tuple [sku; order_id; quantity; available]))
```

- Extend `_lower_raise` to collect `raise`-site arguments; map each
  exception class (from the domain's error types) to a payload schema
  (positional fields, names from the class `__init__`).
- `STry`/handler side: `except InsufficientStockError as e:` lowers to
  a handler guarded by label equality, with `e.<field>` projecting the
  payload; non-matching labels **re-raise** (Python fall-through
  semantics), preserving unwinding.
- `except` without a matching clause: fall to the next handler or
  unwind — same rule.

### B. Adorned-library calls as FunSpec entries (composition)

The SQL theory's `CallRule`s become **opaque calls with contracts** —
exactly what `SnakeletLang`'s unified function table was built for:

```
FunSpec "sql_execute" :
  pre  σ args := ∃ stmt, args = [stmt] ∧ stmt ∈ fragment
                 ∧ table(stmt.table) ∈ σ.store
  post σ args res σ' := per rule:
        Select ⇒ σ'.cursor = π σ(σ_where(table))
      | Insert ⇒ σ'.staged = σ.staged ∪ row  (else Raise "IntegrityError")
      | Update ⇒ σ'.staged = σ.staged[σ_where ↦ sets]
      ∧ σ'.trace = σ.trace ++ [Execute stmt]      -- extends_by_one, native
      ∧ (σ.tx ⇒ σ'.store = σ.store)               -- bracket: store frozen in tx
```

- State representation: `TableStore` as `DictModel` dict-of-dicts on
  the heap; `trace` as `list event` (ListPredicates); `cursor`, `tx`
  likewise.  `extends_by_one` is list append with a head-predicate.
- **Exceptional theory calls** (`duplicate key` → `IntegrityError`,
  commit without begin → `TheoryError`) are `Raise`s in the post —
  the same exception channel as domain errors (§A).  One model for
  theory errors and domain errors.
- Lowering side: `_lower_call` intercepts calls whose receiver is of
  adorned type (`conn`, `cursor`, engine) — the heap-builtins
  precedent (`ref/load/store`) — and emits `SApp "sql_execute" ...`.
  Receiver-type tracking stays conservative: `connect()` returns a
  connection; anything untracked fails loudly.

### C. Exceptional postconditions in contract compilation

`ExcExit` clauses currently compile nowhere on the Iris path.
`wp_exn`'s `Result`-indexed postcondition is the target shape:

```
WP body {{ res. match res with
        | RVal v        ⇒ ensures(before, args, v, after)
        | RErr (lbl, p) ⇒ ∃ exit ∈ contract.exceptions,
                          lbl = exit.raises.label
                          ∧ exit.ensures(before, args, (lbl, p), after)
        end }}
```

- `contract_ir_iris` gains the exit-arm compilation (RaisesExpr path,
  currently a `True` stub); each `ExcExit` contributes one disjunct.
- The **exit coverage obligation** (O4) falls out for free: if the
  body's raise matches no declared exit, the postcondition is
  unsatisfiable — the proof fails, which is the check.

### D. The conservative Python fragment (acceptance discipline)

The lowerer accepts exactly this, and refuses everything else loudly
(`UnsupportedConstruct`, the `IrisGenError` pattern):

- statements: assignment, aug-assign, `if/elif/else`, `return`,
  `raise`, `try/except E [as x]` (multiple clauses), expression
  statements, `with <adorned connect> as <name>` (inert CM protocol)
- expressions: the ContractLinter-covered pure fragment (arithmetic,
  comparison, boolean ops, attribute/subscript on fragment values,
  tuple building, dataclass construction, calls to adorned methods or
  pure helpers)
- values: ints, strings, bools, tuples, dataclass instances, dicts
  (DictModel), lists (ListPredicates)
- **not** in the fragment: loops (v2 — SWhile exists but our services
  don't need it), mutation of locals captured in closures, generators,
  `*args/**kwargs`, `global`/`nonlocal`, async

#### D.1 Value model and guarded typing

Lowering `products[sku].reserved` straight to `Z` silently assumes an
integerness Python never promised.  The conservative discipline:

**variables default to an arbitrary-value type; a typed view is
introduced only under a guard.**  The value model is a universal sum
(SnakeletLang's `sn_val` shape: `LitInt | LitBool | LitString |
LitTuple | LitExn | …`); a `Z`-typed view of a variable is introduced
only when a guard establishes the type.

Guard sources, in order of strength — all three already exist:

1. **Schema + projection (global, discharged once).**  `state_schema`
   `type_hint`s plus the projection's construction discipline
   (dataclass instances built from driver values) establish a typing
   context `Γ` over observed-state scalars; the fidelity suite
   validates it against reality continuously.  Ground, discharged
   once — never re-proven per clause.
2. **Witness builders (runtime guards).**  `build_witness`'s
   `int(row[...])` conversions are the args-side guards, materialized:
   Gherkin strings become honest ints at the boundary.
3. **Local guards (flow refinement).**  `if isinstance(x, int): …`
   lowers to an `IsShape` fact (`contract_ir` already has
   `IsShape`/`IsValid`), refining the variable in its scope.

Obligations carry `Γ` as premises — `Γ ⊩ products_S1_reserved : int`
— so the arithmetic core stays in linear-arithmetic land, but
*soundly*: the integerness assumption is explicit and justified, not
smuggled in by a naming scheme.

**The adornment boundary is where this bites.**  Anything returned by
a library call (a fetched row, a cursor value) crosses in as an
arbitrary value and must be guarded before use — so the SQL theory's
CallRules state the types of fetched values as postconditions
(schema-derived: `fetchone` on `products` returns `(int, int, int)`),
making boundary guards a theory obligation rather than hope.

**The failure this prevents:** a poisoned row (`reserved` arrives as
a string from a misbehaving driver) makes an unguarded Z-model
*silently agree*; under guarded typing the premise
`Γ ⊩ reserved : int` is exactly what fails — loudly, at the boundary,
where the fidelity harness can catch it.

---

## 3. Obligation emission (unchanged style — dump first)

Per operation, one WP obligation in the shape of §C; per contract the
O-series from the system design doc (consistency, exception
consistency, exit coverage, invariant preservation, derived soundness,
sequence lemmas).  Emit as independent lemmas, portfolio automation
(`lia`, `congruence`, `sauto`, SMTCoq), three-valued scoreboard
(PROVED / DISPROVED / UNKNOWN), LLM disproof on UNKNOWNs with
executable-model validation.  Staged `SnakeletExnTactics` scripts are
the escalation path — the script is the trace.

Sequence lemmas (O7) compose proven ops **opaquely**: after an op's WP
obligation closes, the op joins the client-callable table as a
`FunSpec` — `wp_call` chains `reserve → release → restock` without
re-entering bodies.  This is the compositionality the theory's
CallRules promised, one level up.

---

## 4. Validation

1. **Lowering fidelity** — the lowered model executes (SnakeletEval,
   extended to `Try`/`Raise` if not already covered) against the same
   Gherkin rows as the runtime runner: trace equality with the stub,
   which has fidelity with SQLite.  Three worlds, one observable
   behaviour.
2. **Exception dispatch fidelity** — for every `error:` row in the
   existing features, the lowered model raises the same label with the
   same payload (fields), and the handler/dispatch path matches the
   Python semantics (re-raise fall-through included).
3. **Counterexample execution** — LLM-disproof candidates are checked
   by executing the lowered model, not just the Python predicates.

---

## 5. Work order

1. **Payload exceptions** — `_lower_raise` field payloads + label-guarded
   `except` dispatch with re-raise fall-through (A).  Smallest, unblocks
   everything; the Coq side already supports it.
2. **Theory FunSpecs** — SQLTHEORY → Coq table generator (B); TableStore
   on DictModel, trace on ListPredicates.
3. **Adorned-call lowering** — `_lower_call` interception per registry (B).
4. **Exceptional post compilation** — `contract_ir_iris` exit arms (C).
5. **First dump** — inventory domain obligations end-to-end; scoreboard.
6. **Sequence lemmas via wp_call** (O7).
7. **Value-model wiring** — contract_ir_iris list/dict nodes off the
   `True` stubs, onto DictModel/ListPredicates.

## 6. Open questions

- Does `SnakeletEval.v` cover `Try`/`Raise` already?  (Determines
  whether validation step 1 needs Coq work or is free.)
- `with` lowering for adorned context managers that *aren't* inert
  (file handles later) — v1 only supports the inert `connect()` case.
- `try/finally` and `else` arms — excluded from the fragment for v1;
  add only when a consumer appears.
