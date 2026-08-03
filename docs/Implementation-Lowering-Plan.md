# Implementation Lowering: Python AST → SnakeletExn

## Why this is hard

Implementation lowering must translate an arbitrary Python service function
into a SnakeletExn program and prove the lowered program refines the
generated FunSpecS contract specification.

The Python function is not a mathematical predicate (which is what the
contract lowering handles).  It is an imperative program with:

- SQLAlchemy calls (`conn.execute`, `.fetchone`)
- Transaction boundaries (`engine.begin()`)
- Control flow (branches, returns)
- Exceptions with structured payloads (`raise InsufficientStockError(sku,
  qty, available)`)
- Python-level variable binding and arithmetic

Each of these must be mapped to a corresponding SnakeletExn construct.

## Approach: two-stage pipeline

### Stage 1 — Python AST → SnakeletExn AST (`lower_impl.py`)

A new module `specsaver/lower/impl_lower.py` containing a function:

```python
def lower_impl(func, contract_info: ContractInfo) -> sn_expr:
    """Lower a Python service function into a SnakeletExn expression."""
```

The function uses Python's `ast` module to parse the function body, then
recursively lowers each statement into a SnakeletExn expression.

### Stage 2 — Proof generation (`emit_impl_proof`)

Once the lowered AST exists, we generate a Coq lemma proving that the
lowered program satisfies the contract's FunSpecS:

```coq
Lemma lowered_impl_satisfies_spec : forall sigma vs,
  gen_pre sigma vs ->
  WPE (lowered_expression) {{ λ r,
    exists ups, gen_post sigma vs r ups /\ updates_dom_in sigma ups }}.
```

## Mapping: Python constructs → SnakeletExn

### Expressions

| Python | SnakeletExn |
|--------|-------------|
| `x + y`, `x - y` | `BinOp AddOp/SubOp e1 e2` |
| `x < y`, `x == y` | `BinOp LtOp/EqOp e1 e2` |
| `row[0]`, `row.on_hand` | `Call "dict_lookup_str" [e; LitString field]` (transparent) |
| `x is None` | `BinOp EqOp (Call "dict_lookup_str" ...) (Val LitUnit)` |

### Statements

| Python | SnakeletExn |
|--------|-------------|
| `x = expr` | `Let "x" lower(expr) lower(rest)` |
| `if cond: body` (no else) | `If lower(cond) lower(body) (Val LitUnit)` |
| `if cond: body else: alt` | `If lower(cond) lower(body) lower(alt)` |
| `return expr` | `Val lower(expr)` |
| `raise E(args)` | `Raise (Val (LitExn "E" (LitTuple lower_args)))` |

### SQLAlchemy calls (via the theory registry)

| Python | SnakeletExn (syntactic) | Proof step |
|--------|-------------------------|------------|
| `conn.execute(text(SQL), params)` | `Call "conn.execute" [text_sql; params]` | `wp_call` with theory's FunSpecS |
| `.fetchone()` | `Call "conn.fetchone" []` | `wp_call` with FunSpecS |
| `engine.begin()` | Wraps body in `Try` | `wp_try` + transaction handling |

### Adorned call lowering

For SQLAlchemy calls, the lowerer looks up the callable in the theory's
adornment registry (`specsaver.theory.sql.SQLTHEORY`).  The `translate_sql`
function maps the SQL string to a theory action model.  This is the same
mechanism the `_lower_call` specification from the design docs describes.

## SnakeletExn target expressions

For `restock_body`, the lowered expression is:

```coq
Let "store_d" (Load (Val (LitLoc store_loc))) (
Let "row_opt" (Call "dict_lookup_str" [Val (LitString sku); Var "store_d"]) (
Let "_check" (If (BinOp EqOp (Var "row_opt") (Val LitUnit))
                 (Raise (Val (LitExn "ProductNotFoundError" LitUnit)))
                 (Val LitUnit)) (
Let "on_hand" (Call "dict_lookup_str"
                      [Val (LitString "on_hand"); Var "row_opt"]) (
Let "reserved" (Call "dict_lookup_str"
                      [Val (LitString "reserved"); Var "row_opt"]) (
Let "new_row" (Call "row_of"
                      [BinOp AddOp (Var "on_hand") (Val (LitInt qty));
                       Var "reserved";
                       ...]) (
Let "new_store" (Call "dict_insert_str"
                      [Val (LitString sku);
                       Var "new_row";
                       Var "store_d"]) (
Let "_" (Store (Val (LitLoc store_loc)) (Var "new_store"))
    (Val (LitDict receipt_fields))
))))))
```

## Proof strategy

The refinement proof follows the SnakeletExn WP calculus:

```
wp_bind       — enter the evaluation context
wp_load/wp_store — heap operations
wp_pure_step  — transparent function calls (row_of, dict_lookup_str)
wp_bind_item  — compositionality of let-binding and evaluation contexts
wp_call       — opaque calls (FunSpecS entries for SQLAlchemy operations)
wp_raise/wp_try — exception handling
wp_value      — terminal values (return)
```

The proof builds up from the inner expression outward: prove the return
value satisfies the post, then the `Store`, then the `dict_insert_str`
call, and so on up the let-chain.

## The theory bridge

The SQL theory provides FunSpecS entries for each adorned call:

```
Definition sql_theory_table (f : string) : option fun_entry :=
  if String.eqb f "conn.execute" then
    Some (FunSpecS execute_pre execute_post)
  else ...
```

The lowering uses these entries in `wp_call` to prove that each SQL
operation produces the expected state update.  The differential validation
suite that tests the stub against real SQLite provides empirical evidence
that these FunSpecS entries correctly model the real library.

## Incremental plan

### Phase 1: Pure Python fragment (no SQLAlchemy, no exceptions)

Lower a simple function like:

```python
def add_one(x: int) -> int:
    y = x + 1
    return y
```

Prove the lowered program satisfies a trivial contract.  Establishes the
lowerer pipeline and proof machinery.

### Phase 2: Dict operations (row_of, dict_lookup_str, dict_insert_str)

Lower the table-level operations (no SQLAlchemy calls — work directly
with the store dict).  Lower a function that reads/writes the dict.

### Phase 3: Transactions + SQLAlchemy calls

Lower the full `engine.begin()` + `conn.execute` + `fetchone` pattern.
Wire through the theory's FunSpecS entries for SQL calls.  Prove the
lowered transaction body satisfies the contract's gen_post.

### Phase 4: Exceptions

Lower `raise` + `except` handling.  Prove that exception paths satisfy
the contract's exception FunSpecS entries.

### Phase 5: Full service lowering

Lower the complete `reserve`, `release`, `restock`, and `transfer`
functions.  Prove each against its contract.
