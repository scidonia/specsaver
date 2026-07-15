# Contract Language Specification

## 1. Overview

The contract language is a **pure, typed fragment of Python** used to express
the semantic content of preconditions, postconditions, frame conditions,
invariants, and effect specifications.

Every contract construct is executable Python.  It is also statically
analysable: its AST is the input to SMT translation, proof generation, and
property-based test generation.  The contract language is the **single source of
semantic truth** — no testing or verification artifact may introduce
independent semantics.

---

## 2. Purity

Contracts must be **pure**.  A pure contract:

1. performs **no mutation** of any reachable object;
2. performs **no I/O** (no filesystem, no network, no `print`, no `input`);
3. accesses **no global or module-level mutable state**;
4. is **deterministic** — the same arguments always produce the same result;
5. catches **no exceptions** (contracts must not depend on exception-driven
   control flow).

Concretely, the following Python constructs are **forbidden** inside contracts:

- assignment to anything other than a local variable introduced by the
  contract body;
- `del`, `global`, `nonlocal`;
- `try`/`except`/`finally`;
- `with` statements;
- `yield`, `yield from`, `await`;
- any call to a function not known to be pure (the purity of every callee is
  statically verified);
- class definitions, `lambda` (until lambda purity is resolved);
- `import` statements (imports are resolved at contract-registration time,
  not at contract-evaluation time).

**Allowed constructs** include:

- arithmetic, boolean, comparison, and bitwise operators;
- `if`/`elif`/`else`;
- `for` loops over finite iterables;
- `while` loops (with explicit termination measures — see §3.4);
- pure function calls (including recursion — see §3.6);
- comprehensions (`list`, `set`, `dict`, generator) whose element expressions
  are pure;
- `all(...)`, `any(...)`, `sum(...)`, `len(...)`;
- tuple unpacking and pattern matching against literal constructors.

---

## 3. Type Discipline

### 3.1 Mandatory Type Annotations

Every contract-level name **must** carry a type annotation.  This includes:

- function parameters;
- return types;
- local variables bound in comprehensions (inferred where possible, explicit
  otherwise);
- ghost variables (see §7).

No contract is accepted by the registry unless every name is annotated or
unambiguously inferred from a `NewType`, `TypeAlias`, or literal.

### 3.2 The `Any` Type

`Any` is the **top type** of the contract type system.  It is the sum of all
possible Python types:

```
Any = int | float | str | bytes | bool | None | list[Any] | dict[Any, Any]
    | set[Any] | tuple[Any, ...] | Callable[..., Any] | type | object | ...
```

`Any` carries **no static information**.  A value of type `Any` supports no
operations until it is refined by a dynamic type guard:

```python
@predicate
def safe_division(x: Any, y: Any) -> bool:
    return isinstance(x, (int, float)) and isinstance(y, (int, float)) and y != 0
```

When a name has type `Any`, the verifier treats it as an opaque, unbounded
value.  Property-based test generators **must not** attempt to generate
arbitrary `Any` values — the contract must refine `Any` to a concrete type
before use.

### 3.3 Supported Type Constructors

| Constructor          | Example                                |
|----------------------|----------------------------------------|
| primitives           | `int`, `float`, `str`, `bytes`, `bool` |
| `None`              | `None`                                 |
| `list[T]`           | `list[int]`                            |
| `dict[K, V]`        | `dict[str, float]`                     |
| `set[T]`            | `set[str]`                             |
| `tuple[T, ...]`     | `tuple[int, str]`, `tuple[int, ...]`   |
| `Optional[T]`       | `Optional[int]`  (= `T | None`)        |
| `Union[T1, T2, ...]`| `Union[int, str]` (= `T1 | T2`)        |
| `Callable[[A1, ...], R]` | `Callable[[int], bool]`           |
| `Literal[v1, ...]`  | `Literal["active", "closed"]`          |
| `NewType`           | `UserId = NewType("UserId", int)`      |
| `TypeAlias`         | `Vector = list[float]`                 |
| `Any`               | any possible Python value              |

Recursive types are permitted only through `TypeAlias` indirection.

### 3.4 Termination

`for` loops are guaranteed to terminate because they iterate over finite
collections.

Recursion and `while` loops must be provably terminating.  The contract
system accepts three forms of termination argument:

#### Structural Recursion

A recursive call on a **syntactically smaller sub-term** of an argument is
structurally terminating.  The verifier recognises destructuring of
`list[T]` (e.g. `xs[1:]`), `tuple[T, ...]`, and user-defined algebraic
types:

```python
@predicate
def list_length(xs: list[Any]) -> int:
    if not xs:
        return 0
    return 1 + list_length(xs[1:])
```

Here `xs[1:]` is a structural sub-term of `xs`, so termination is automatic.
No explicit measure is required.

#### Lexical Descent on Integers

A recursive call whose controlling integer argument strictly decreases
toward a fixed lower bound (typically `0`) is terminating:

```python
@predicate
def sorted_upto(xs: list[int], i: int) -> bool:
    if i >= len(xs) - 1:
        return True
    return xs[i] <= xs[i + 1] and sorted_upto(xs, i + 1)
```

Here `i + 1` moves strictly toward the upper bound `len(xs) - 1`, so the
recursion is bounded.  Mutually recursive lexical descent (where two or more
functions decrease on a shared ordering) is also accepted.

#### Explicit Measure (escape hatch)

When the termination argument cannot be inferred — complex `while` loops,
non-obvious mutual recursion, or recursion on a derived measure — the
contract may carry an explicit `@measure` decorator with a non-negative
integer expression that strictly decreases on each iteration:

```python
@predicate
@measure(lambda n: n)
def collatz_steps(n: int) -> int:
    if n <= 1:
        return 0
    if n % 2 == 0:
        return 1 + collatz_steps(n // 2)
    return 1 + collatz_steps(3 * n + 1)
```

---

## 4. Contracts

Every operation is described by a bundle of named semantic propositions.

### 4.1 Preconditions

A **precondition** is a pure predicate over the operation's input arguments and
the current state:

```
Pre(state: S, args: A) -> bool
```

Where `S` is the state type of the owning component and `A` is the **Args**
type of the operation (§4.4) — a single structured input object, not a
scattered argument list.

```python
@precondition(entry_point="transfer")
def transfer_pre_valid_amount(state: AccountState, args: TransferArgs) -> bool:
    return args.amount > 0 and args.amount <= state.source.balance
```

### 4.2 Postconditions

A **postcondition** is a pure predicate relating the old state, the input, the
result, and the new state:

```
Post(old_state: S, args: A, result: R, new_state: S) -> bool
```

Where `R` is the **Result** type of the operation (§4.4) — a single
structured output object, not multiple return values.

```python
@postcondition(entry_point="transfer")
def transfer_post_total_preserved(
    old_s: AccountState, args: TransferArgs, result: TransferReceipt, new_s: AccountState
) -> bool:
    return (
        old_s.source.balance + old_s.target.balance
        == new_s.source.balance + new_s.target.balance
    )
```

### 4.3 Invariants

An **invariant** is a predicate over a single state that holds at every visible
quiescent point:

```
Inv(state: S) -> bool
```

```python
@invariant
def account_balance_non_negative(state: AccountState) -> bool:
    return all(a.balance >= 0 for a in state.accounts.values())
```

Invariants may reference **ghost state** (see §7).  An invariant must be
re-established after every operation that modifies the owning component.

### 4.4 Entry Points and Canonical Signatures

Every contract may declare the **entry point** (operation) it belongs to via
`entry_point="<name>"`.  This is what makes the full contract for an
operation *discoverable as a set*, rather than a naming convention a test
author has to remember:

```python
registry.preconditions_for("transfer")   # -> every precondition for `transfer`
registry.postconditions_for("transfer")  # -> every postcondition for `transfer`
registry.invariants_for("transfer")      # -> every invariant tagged for `transfer`
```

For this to work, **every precondition/postcondition sharing an
`entry_point` must use the same input and output types.**  No matter how
many fields an operation's input has — ten, or a hundred — the contract
signature never grows past `Pre(state, args)` / `Post(old_state, args,
result, new_state)`.  Additional data is encoded as fields on a single
**Args** (input) and **Result** (output) object:

```python
@dataclass(frozen=True)
class TransferArgs(Args):
    source_id: str
    target_id: str
    amount: int

@dataclass(frozen=True)
class TransferReceipt(Result):
    transaction_id: str
    source_id: str
    target_id: str
    amount: int
    success: bool
```

`Args` and `Result` are frozen-dataclass base classes.  Subclasses must
also be frozen — Python enforces this automatically, since a dataclass
cannot mix frozen and non-frozen bases — which is exactly the immutability
discipline purity requires: a precondition/postcondition must never be
able to mutate the input or output it is asserting properties about.

This is enforced **at registration time**, not merely by convention:

- The `args` parameter of any precondition/postcondition tagged with
  `entry_point` must be annotated with an `Args` subclass; the `result`
  parameter of any such postcondition must be annotated with a `Result`
  subclass.  An untyped or wrongly-typed parameter is rejected immediately.
- Every contract sharing the same `entry_point` must agree on exactly
  which `Args`/`Result` subclass it uses.  A second precondition
  registered under an already-used `entry_point` with a *different* Args
  type raises a `ValueError` immediately — this is caught at import time,
  not later as a call-time `AttributeError` on a missing field.

Contracts that omit `entry_point` (reusable `@predicate`s, `@function`s,
one-off checks) are not subject to this constraint and remain free-form.

When an operation's input genuinely has mutually exclusive shapes (e.g.
"search by name" vs. "search by date range" vs. "search by geo box"),
prefer either a discriminated union (`Union[NameSearch, DateRangeSearch,
...]` tagged with a `Literal` discriminant) or, more often, separate
entry points — one canonical Args/Result pair per behaviourally distinct
operation.

See `specsaver.verify.run_entry_point`, which executes every currently
registered contract for an entry point around a call to the
implementation, so that adding a new precondition/postcondition is
automatically picked up by every test that calls it — nothing needs to be
hand-listed.

---

## 5. Frame Conditions

Frame conditions are **separate semantic objects** — they are not embedded in
arbitrary pre/post code.

### 5.1 Writes Frame

A **writes frame** declares every component of the state that an operation
**may modify**:

```python
@writes
def transfer_writes_frame() -> Frame:
    return Frame(
        writes={
            Field("source.balance"),
            Field("target.balance"),
            Field("audit_log"),
        }
    )
```

If a field is not listed in the writes frame, the operation **must not** modify
it.  This is a compile-time obligation: the verifier must prove that every
write in the implementation body is covered by the declared frame.

### 5.2 Reads Frame

A **reads frame** declares every component of the state that an operation
**may read** (in addition to those it writes):

```python
@reads
def transfer_reads_frame() -> Frame:
    return Frame(
        reads={
            Field("source.balance"),
            Field("target.balance"),
        }
    )
```

### 5.3 Environmental Reads

If an operation reads anything outside its own state — configuration,
environment variables, the system clock, remote service state — it **must**
declare this in its reads frame using distinguished field paths:

```
Field("env.SOURCE_ACCOUNT_ID")
Field("env.clock.now")
Field("env.config.max_transfer_amount")
```

An undeclared environmental read causes the contract to be **rejected** at
registration time.

### 5.4 Frame Syntax

```
Frame ::= Frame(writes=Set[Field], reads=Set[Field])

Field ::= Field("<dotted.path>")
```

Fields are hierarchical: declaring `Field("source")` covers all sub-paths
(`source.balance`, `source.id`, etc.).

---

## 6. Effect Specifications

Effects are **declarative side-effect signatures** that describe what an
operation does to the outside world.

```python
@effect
def transfer_effect_audit_event() -> EffectSpec:
    return EffectSpec(
        opens=set(),          # connections opened
        uses={"database"},    # connections used
        emits={Event("audit.transfer_completed")},
    )
```

### 6.1 Connection Declarations

| Keyword   | Meaning                                                |
|-----------|--------------------------------------------------------|
| `opens`   | This operation **creates** a new connection/resource.  |
| `uses`    | This operation relies on an already-open connection.   |
| `closes`  | This operation **releases** a connection/resource.     |

```python
@effect
def init_database_effect() -> EffectSpec:
    return EffectSpec(
        opens={"database", "cache"},
    )
```

### 6.2 Event Declarations

An effect may declare the set of observable events the operation can emit:

```python
@effect
def transfer_effect() -> EffectSpec:
    return EffectSpec(
        uses={"database"},
        emits={
            Event("audit.transfer_completed"),
            Event("notification.funds_received"),
        },
    )
```

### 6.3 Effect Composition

Effects compose monotonically: if operation `A` calls operation `B`, the
effect of `A` is the union of its own declared effects and those of `B`.

---

## 7. Ghost Variables

Ghost variables are specification-only state that exists in the contract model
but **not** in the implementation.  They serve the same role as ghost
variables in Dafny: they allow the specification to track abstract state that
the implementation does not physically store.

### 7.1 Declaration

```python
@ghost
class TransferLimits:
    daily_remaining: int
    monthly_remaining: int
    per_transfer_max: int
```

Ghost types are annotated just like any other type.  A ghost field may hold
`Any` if its shape is not yet determined.

### 7.2 Ghost State in Invariants

```python
@invariant
def limits_not_exceeded(state: AccountState, ghost: TransferLimits) -> bool:
    return (
        ghost.daily_remaining >= 0
        and ghost.monthly_remaining >= 0
    )
```

### 7.3 Ghost Updates in Postconditions

Ghost variables are treated as part of the state for the purpose of
postconditions.  An operation may update ghost state even though no physical
state changes:

```python
@postcondition
def transfer_post_ghost_limits(
    old_s: AccountState,
    amount: int,
    result: TransferReceipt,
    new_s: AccountState,
) -> bool:
    return (
        new_s.ghost.daily_remaining
        == old_s.ghost.daily_remaining - amount
    )
```

### 7.4 Ghost Code

Ghost code is specification-only code that updates ghost variables.  It is
written in the same pure language as contracts but is **not** compiled into
the production implementation:

```python
@ghost_update
def update_transfer_limit_ghost(ghost: TransferLimits, amount: int) -> TransferLimits:
    return TransferLimits(
        daily_remaining=ghost.daily_remaining - amount,
        monthly_remaining=ghost.monthly_remaining - amount,
        per_transfer_max=ghost.per_transfer_max,
    )
```

Ghost code is verified as a contract entry point in its own right.

---

## 8. Quantification

The contract language supports quantifiers for expressing properties over
collections.

### 8.1 Universal Quantification

```python
@predicate
def all_balances_positive(state: AccountState) -> bool:
    return forall(state.accounts.values(), lambda a: a.balance >= 0)
```

Syntactic sugar via comprehensions:

```python
return all(a.balance >= 0 for a in state.accounts.values())
```

Abstract (potentially infinite) domains:

```python
@predicate
def sum_of_squares_non_negative() -> bool:
    return forall((x for x in Z), lambda x: x * x >= 0)
```

### 8.2 Existential Quantification

```python
@predicate
def exists_sufficient_account(state: AccountState, amount: int) -> bool:
    return exists(state.accounts.values(), lambda a: a.balance >= amount)
```

Syntactic sugar:

```python
return any(a.balance >= amount for a in state.accounts.values())
```

Abstract domains:

```python
@predicate
def exists_large_prime() -> bool:
    return exists((n for n in N), lambda n: is_prime(n) and n > 1000)
```

### 8.3 Binders

`forall` and `exists` bind over a **set comprehension** domain.  The domain
may be concrete (an explicit collection) or abstract (an infinite set
described by a comprehension or a type):

```python
# Concrete (finite) domain
forall(a for a in state.accounts.values(), lambda a: a.balance >= 0)

# Abstract (potentially infinite) domain
forall(n for n in range(0, 10**12), lambda n: n * n >= 0)
forall(x for x in Z, lambda x: x + 1 > x)
exists(n for n in N, lambda n: is_prime(n) and n > 1000)
```

When the domain is infinite or unbounded, runtime evaluation is not required
— the quantifier is treated as a logical assertion for the SMT solver and
proof backends.  Property-based testing may sample a finite subset of the
domain as an approximation.

---

## 9. Temporal Constructs

### 9.1 `old(...)`

Within a postcondition, `old(expression)` evaluates the expression in the
pre-state:

```python
@postcondition
def balance_decreased(old_s: AccountState, amount: int, result: TransferReceipt, new_s: AccountState) -> bool:
    return new_s.source.balance == old(old_s.source.balance) - amount
```

`old(...)` is syntactic sugar for referencing the `old_*` parameters.  The
verifier desugars `old(E)` into the corresponding projection from the
old-state argument.

### 9.2 `unchanged(...)`

```python
@postcondition
def accounts_unchanged_except_source(
    old_s: AccountState, amount: int, result: TransferReceipt, new_s: AccountState
) -> bool:
    return unchanged(old_s, new_s, except_={Field("source.balance")})
```

`unchanged(old_s, new_s)` asserts that every field reachable from the state
root is equal in `old_s` and `new_s`.  The optional `except_` set carves out
fields that are permitted to change.

---

## 10. Recursion

Contracts may call themselves or other contracts recursively.  Termination is
ensured by structural, lexical, or explicit measures (see §3.4).  The verifier
synthesises a termination proof for every recursive contract.  Contracts that
cannot be proved terminating are rejected.

```python
@predicate
def sorted_upto(xs: list[int], i: int) -> bool:
    if i >= len(xs) - 1:
        return True
    return xs[i] <= xs[i + 1] and sorted_upto(xs, i + 1)
```

Mutual recursion is supported provided the call cluster collectively
terminates under a shared well-founded ordering.

---

## 11. Contract Decorators

Every contract proposition carries exactly one decorator that classifies it:

| Decorator         | Meaning                                      |
|-------------------|----------------------------------------------|
| `@precondition`   | Predicate on `(state, args)`                 |
| `@postcondition`  | Predicate on `(old_state, args, result, new_state)` |
| `@invariant`      | Predicate on `(state)`                       |
| `@predicate`      | Pure, reusable boolean function              |
| `@function`       | Pure, reusable non-boolean function          |
| `@writes`         | Frame: fields the operation may modify       |
| `@reads`          | Frame: fields the operation may read         |
| `@effect`         | Side-effect signature (connections, events)  |
| `@ghost`          | Ghost type or ghost variable declaration     |
| `@ghost_update`   | Ghost-only state transformer                 |
| `@measure`        | Explicit termination measure (escape hatch; see §3.4) |

Every decorator except `@ghost`/`@measure` accepts three optional keyword
arguments: `entry_point` (§4.4 — groups contracts by operation and enforces
canonical Args/Result types), `from_gherkin` (the Gherkin step it flows
from), and `feature` (the feature file it belongs to).

---

## 12. Contract Registry

Every contract proposition is registered with a stable, fully-qualified
identifier:

```
<component>.<category>.<name>
```

Examples:
```
transfer.pre.valid_amount
transfer.post.total_preserved
transfer.post.source_decreased
transfer.frame.account_only
transfer.effect.audit_event
transfer.ghost.limits
```

The registry records for each identifier:

- the **implementation** (the Python function body);
- the **contract kind** (pre, post, invariant, etc.);
- **dependencies** (which other contracts this one calls);
- **proof status** (unverified, verified, counterexample found);
- **testing status** (untested, tested, flaky);
- the **source location** (file, line, column).

---

## 13. Well-Formedness Rules

A contract is **well-formed** iff:

1. Every name is type-annotated or inferred.
2. The body is pure (no mutation, no I/O, deterministic).
3. All callees are themselves pure contracts.
4. Recursive and looping constructs are provably terminating (structural,
   lexical, or via `@measure`).
5. Frame declarations are exhaustive — every read and write in the
   implementation is covered.
6. Environmental reads are explicitly declared.
7. Effects list all connections opened, used, or closed.
8. Ghost state is not referenced in non-ghost implementation code.

Contracts that violate any of these rules are **rejected at registration
time** and may not be referenced by Cucumber steps, property tests, or
verification backends.

---

## 14. Extensibility

The contract language is designed to grow.  Future versions will add:

- **sequence** and **map** abstract types (beyond `list`/`dict`);
- **finite set** theory operations (union, intersection, cardinality);
- **separation-logic** assertions for heap-manipulating code;
- **ownership** annotations for aliasing control;
- **refinement** as a first-class language construct;
- **temporal logic** for liveness properties.

All extensions are required to preserve executability: every contract must
remain directly runnable as Python.
