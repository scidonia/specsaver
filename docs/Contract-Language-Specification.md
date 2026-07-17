# Contract Language Specification

## 1. Overview

The contract language is a **pure, typed fragment of Python** used to express
the semantic content of preconditions (admissibility), postconditions
(transitions), invariants, exception contracts (raises/ORaise), frame
conditions, and effect specifications.

Every contract construct is executable Python.  It is also statically
analysable: its AST is the input to SMT translation, proof generation, and
property-based test generation.  The contract language is the **single source of
semantic truth** — no testing or verification artifact may introduce
independent semantics.

Contracts are **external to the implementation**.  They are declared in a
standalone module and reference an existing function by name — the
implementation is never modified.  Two declaration styles are supported:

1. **Standalone** — ``Contract(impl, args_type=..., feature=..., ...)`` for
   existing (brownfield) code.
2. **Decorator** — ``@contract(args_type=..., feature=..., ...)`` on a new
   implementation class.

Both produce an identical ``Contract`` object holding all predicates in
one place.  The ``Contract`` is the primary API; the older per-contract
decorator registry (``@precondition``/``@postcondition``/``@invariant``
registered individually) remains available for backward compatibility
but is not used by the current test harness or CLI tools.

See the *Specification-Driven Testing Architecture* document for the
full design and step-by-step guide.

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
Contracts are grouped by **feature** (the ``.feature`` filename, e.g.
``"transfer.feature"``) rather than by an arbitrary operation name.  This
is what makes the full contract for an operation *discoverable as a set*:

```python
registry.list_by_feature_and_kind("transfer.feature", ContractKind.PRECONDITION)
registry.list_by_feature_and_kind("transfer.feature", ContractKind.POSTCONDITION)
registry.list_by_feature_and_kind("transfer.feature", ContractKind.INVARIANT)
```

Each contract carries a ``from_gherkin`` string matching the Gherkin
step text it flows from, and a ``feature`` naming the file it belongs to.
One-to-one association is canonical — no shared implici
t ANDs between
contracts.

### 4.1 Preconditions (Admissibility)

A **precondition** is a pure predicate over the current **SpecState** and
the operation's input.  These are *caller obligations* — if they fail,
the implementation is never invoked (``outcome: rejected`` in the
Gherkin).

```
Pre(state: SpecState, args: Args) -> bool
```

```python
@precondition(
    from_gherkin='an account "<source>" with balance <source_balance>'
    ' in currency "<source_currency>"',
    feature="transfer.feature",
)
def transfer_pre_source_exists(
    state: TransferSpecState, args: TransferArgs
) -> bool:
    return args.source_id in state.observed.accounts
```

### 4.2 Postconditions (Transitions)

A **postcondition** is a pure predicate relating the old state, the
input, the result, and the new state:

```
Post(old_state: SpecState, args: Args, result: Result | Exception, new_state: SpecState) -> bool
```

Postconditions self-guard on result type — success-only postconditions
return ``True`` for error outcomes, and vice versa:

```python
@postcondition(
    from_gherkin="the source balance decreased by the transfer amount",
    feature="transfer.feature",
)
def transfer_post_source_decreased(
    old_s: TransferSpecState,
    args: TransferArgs,
    result: TransferReceipt | TransferError,
    new_s: TransferSpecState,
) -> bool:
    if not isinstance(result, TransferReceipt):
        return True   # only applies to successful transfers
    return new_s.observed.accounts[args.source_id].balance == ...
```

### 4.3 Invariants

An **invariant** is a predicate over a single state that holds at every
visible quiescent point.  Invariants attach to Gherkin ``Rule:`` text,
not to individual Given/When/Then steps:

```python
@invariant(
    from_gherkin="All account balances are non-negative at all times",
    feature="transfer.feature",
)
def account_balance_non_negative(state: TransferSpecState) -> bool:
    return forall(state.observed.accounts.values(), lambda a: a.balance >= 0)
```

### 4.4 Exception Contracts

An **exception contract** (``@exceptional``) declares that a specific
Python exception type is raised under a specific condition.  This follows
axiomander's ``raises(ExcType, condition)`` pattern:

```
Exceptional: (state: SpecState, args: Args) -> bool
```

```python
@exceptional(
    exc_type=InsufficientFundsError,
    from_gherkin='an account "<source>" with balance <source_balance>'
    ' in currency "<source_currency>"',
    feature="transfer.feature",
)
def transfer_exc_insufficient_funds(
    state: TransferSpecState, args: TransferArgs
) -> bool:
    return state.observed.accounts[args.source_id].balance < args.amount
```

The exception type's ``code`` class attribute (e.g.
``InsufficientFundsError.code = "INSUFFICIENT_FUNDS"``) bridges the
exception class to the Gherkin ``outcome: error:INSUFFICIENT_FUNDS``
column.  At runtime the runner catches exceptions, matches them to
``@exceptional`` contracts by code, and verifies the condition held.

Exception contracts are distinct from preconditions: preconditions block
execution; exception contracts describe outcomes that occur *after*
admissibility is satisfied.

### 4.5 Canonical Signatures

Every precondition/postcondition/invariant/exceptional shares the same
parameter structure, making the full contract callable uniformly by the
scenario runner:

| Kind           | Signature                                    |
|----------------|----------------------------------------------|
| ``@precondition``  | ``(state, args) → bool``                  |
| ``@postcondition`` | ``(old_state, args, result, new_state) → bool`` |
| ``@invariant`` | ``(state) → bool``                           |
| ``@exceptional`` | ``(state, args) → bool``                   |

``Args`` and ``Result`` are frozen-dataclass base classes.  The ``state``
parameter is a domain-specific ``SpecState`` with provenance
decomposition (observed, derived, environment, history, ghost).  See the
*Specification-Driven Testing Architecture* document for the full
design.  The ``result`` parameter may be a ``Result`` subclass (success)
or a Python ``Exception`` (error outcome) — postconditions self-guard
accordingly.

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

## 7. Ghost Variables and SpecState Provenance

The contract-facing state (``SpecState``) is an immutable snapshot with
provenance decomposition.  Not everything that contracts reason about is
"ghost state" — the source of each field matters.

### 7.1 Provenance classes

| Source                   | Classification  | Example                                |
|--------------------------|-----------------|----------------------------------------|
| Database table           | **observed**    | ``accounts``, ``limits`` (from a DB)   |
| Computed from observed   | **derived**     | ``total_balance``                      |
| External runtime         | **environment** | ``current_time``, ``principal``        |
| Interpreted trace        | **history**     | ``logical_events``                     |
| Proof- or spec-only       | **ghost**       | ``initial_total``, linearisation witnesses |

### 7.2 Persistent state is NOT ghost state

State stored in a database table (e.g. transfer limits) is **observed**
state — it has a concrete representation and is recoverable from the
database.  It should be a plain ``@dataclass``, not decorated with
``@ghost``.  Genuine ghost state is proof-only: values that need not
exist in concrete storage and must obey noninterference (changing them
must not alter concrete execution).

### 7.3 Declaration

```python
# Persistent / observed — plain dataclass, stored in a DB table
@dataclass
class TransferLimits:
    per_transfer_max: int | None = None
    daily_remaining: int | None = None
    monthly_remaining: int | None = None

# Genuine ghost — proof-only, not stored in any table
@ghost
@dataclass
class ProofWitness:
    initial_total: int
    linearisation_key: str
```

### 7.4 SpecState structure

```python
@dataclass(frozen=True)
class TransferSpecState:
    observed: TransferObserved       # from the database
    derived: TransferDerived         # computed from observed
    ghost: TransferGhost             # proof-only
```

Contracts access all components uniformly:
``state.observed.accounts[id].balance`` and
``state.observed.limits.per_transfer_max`` and
``state.derived.total_balance``.  The ``@ghost`` decorator marks the
``TransferGhost`` component as specification-only; everything else is
observable.

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

## 9. Temporal and Logical Constructs

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

### 9.3 `implies(p, q)`

Logical implication as a contract expression — makes conditional
structure explicit in a single expression rather than a multi-line
``if``/``return`` guard:

```python
@postcondition(...)
def transfer_post_source_decreased(old_s, args, result, new_s) -> bool:
    return implies(
        isinstance(result, TransferReceipt),
        new_s.observed.accounts[args.source_id].balance
        == old(old_s.observed.accounts[args.source_id].balance) - args.amount,
    )
```

This reads: "If the result is a receipt → the source balance decreased
by the amount."  The definition is ``¬p ∨ q`` — a guard that fails open.
When ``p`` is false (e.g. an exception was raised), ``implies`` returns
``True`` trivially; when ``p`` is true, ``q`` must hold.

```python
def implies(p: bool, q: bool) -> bool:
    return not p or q
```

The error-preservation variant is:

```python
return implies(
    isinstance(result, (TransferError, Exception)),
    old(source_balance) == new(source_balance) and ...,
)
```

"If it's an error → state is unchanged."



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

| Decorator         | Meaning                                        |
|-------------------|------------------------------------------------|
| `@precondition`  | Predicate on `(state, args)` — admissibility  |
| `@postcondition` | Predicate on `(old_state, args, result, new_state)` — transition |
| `@invariant`     | Predicate on `(state)` — holds at every quiescent point |
| `@exceptional`   | Predicate on `(state, args)` — condition that triggers an exception type |
| `@predicate`     | Pure, reusable boolean function               |
| `@function`      | Pure, reusable non-boolean function           |
| `@writes`        | Frame: fields the operation may modify        |
| `@reads`         | Frame: fields the operation may read          |
| `@effect`        | Side-effect signature (connections, events)   |
| `@ghost`         | Ghost type or proof-only state declaration    |
| `@ghost_update`  | Ghost-only state transformer                  |
| `@measure`       | Explici
t termination measure (see §3.4)          |

Every decorator accepts two optional keyword arguments:
``from_gherkin`` (the Gherkin step or Rule text the contract flows from)
and ``feature`` (the ``.feature`` filename).  These are the primary
identification mechanism — contracts are grouped by feature, not by an
arbitrary operation name.  ``@exceptional`` additionally accepts
``exc_type`` (the Python exception class).

The ``entry_point`` parameter is deprecated — it remains accepted for
backward compatibility but is not used by the current feature-based
architecture.

---

## 12. The `Contract` object

Contracts are external to the implementation — they reference an existing
function by name without modifying the function or its class.

### 12.1 Declaration

```python
from specsaver.contract_model import Contract

transfer_contract = Contract(
    TransferService.transfer,    # existing function — never modified
    args_type=TransferArgs,      # explicit frozen dataclass, not derived
    feature="transfer.feature",
    when='funds of <amount> are transferred ...',
    observe=TransferProjection().snapshot,
    requires=[...], ensures=[...], exceptions={...}, invariants=[...],
    ghost_state=..., ghost_init=..., ghost_transitions=[...],
    writes={...}, reads={...}, uses={...}, emits={...},
)
```

The `Contract` object bundles all predicates, frame conditions, effects,
and ghost state for one operation.  The `args_type` is always declared
explicitly — it is never derived from the implementation's positional
parameter order, so the implementation can have any signature.

### 12.2 Decorator variant

```python
from specsaver.contract_model import contract

@contract(args_type=TransferArgs, feature="transfer.feature", ...)
class TransferService:
    def transfer(self, db_path, source_id, target_id, amount):
        ...
```

The decorator auto-discovers the first non-underscore method, creates a
`Contract`, and stores it on ``cls.__specsaver_contract__``.

### 12.3 Invocation

The `Contract.invoke(instance, env, args)` method auto-marshals `Args`
fields to the implementation's parameter names, handling positional,
keyword-only, and default values automatically:

```python
svc = TransferService()
result = contract.invoke(svc, db_path, TransferArgs("A1", "A2", 30))
```

The `invoke` method matches `Args` field names to the implementation's
parameter names — no positional counting, no `env_count` parameter.
`Context[T]` can optionally annotate the environment parameter for
greenfield code, but is never required.

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
