# Specification-Driven Testing Architecture

How Gherkin specifications, contract predicates, implementations,
databases, and auto-derived tests connect — generically, not specific
to the bank transfer example.

This document is the operational companion to the *Symmetric Database
State Specification Architecture* document, which defines the semantic
invariants.  Where the two disagree, the Symmetric document is
authoritative.

---

## 1. The six layers

```
1. Verbal specification
   Gherkin rules, named concepts, and abstract example classes

2. Contract specification
   Domains, SpecState, admissibility, operation cases,
   transitions, frames, invariants, histories, and ghost state

3. Example elaboration
   Example-class constraints → generated ScenarioWitness values

4. Concrete implementation
   Python code operating on a real ExecutionContext

5. Projection and refinement bridge
   materialize(witness) → ExecutionContext
   snapshot(context) → SpecState
   representation and round-trip laws

6. Evidence consumers
   specification tests
   implementation tests
   trace tests
   runtime monitors
   formal verification
```

Layers 1–2 are the **specification**.  Layer 4 is the **system under
test**.  Layers 3 and 5–6 are the **test harness**.  No layer imports
upward: contracts don't import implementation; tests import all layers
but the runner itself depends only on Protocol interfaces and
`OperationContract`.

The projection and refinement bridge (layer 5) is a first-class
layer, not merely a fixture utility.

---

## 2. Layer 1 — Gherkin feature file

### Structure

```gherkin
Feature: <system name>
  <free-text description>

  Rule: <invariant text>           ← attaches to @invariant

  Rule: <business rule text>       ← documentation / grouping

  Scenario Outline: <operation name>
    Given <step 1 text with <placeholders>>
    And   <step 2 text with <placeholders>>
    When  <step text with <placeholders>>
    Then  <step 1 text with <placeholders>>
    And   <step 2 text with <placeholders>>

    Examples: <group name>
      | col1 | col2 | ... | outcome   | [fault] |
      | ...  | ...  | ...  | success   |         |
      | ...  | ...  | ...  | rejected  |         |
      | ...  | ...  | ...  | error:CODE| x       |
```

### Conventions

| Element         | Maps to (layer 2)                |
|-----------------|----------------------------------|
| `Rule:` text    | `@invariant(from_gherkin=...)`   |
| `Given` step    | `@precondition` or `@case` (see §12 of the Symmetric document) |
| `When` step     | `@writes/@reads/@effect(from_gherkin=...)` + the impl signature |
| `Then` step     | `@postcondition(from_gherkin=...)`|
| `outcome` column| `run_scenario` dispatch          |
| `fault` column  | `fault_injector` callback        |

### The `outcome` column

Every Examples row carries an `outcome` column with one of:

| Value            | Meaning                                                |
|------------------|--------------------------------------------------------|
| `success`        | Admissibility holds; impl succeeds; postconditions checked |
| `rejected`       | A business rejection case fires; impl IS called and returns an error |
| `error:<CODE>`   | Admissibility holds; impl invoked; runtime fault returns error with `code` |

**Important**: `rejected` does NOT mean "precondition fails, impl
skipped" — that was the old semantics.  Under the Symmetric
architecture, business rejections (insufficient funds, currency
mismatch) are *operation cases*: the impl is called and returns an
error result.  Only true caller precondition violations (malformed
input) block execution entirely.

---

## 3. Layer 2 — Contract specification

### The execution context

The implementation executes within an `ExecutionContext`:

```python
@dataclass
class ExecutionContext:
    database: DatabaseSession
    environment: RuntimeEnvironment
    trace: EventRecorder
    ghost: GhostStore
```

The exact fields may differ by domain, but the conceptual categories
should remain stable: database, environment, trace, ghost store.

### The specification state

The state visible to contracts is an immutable `SpecState` — a
projection of the execution context, not a direct handle to the
database:

```python
@dataclass(frozen=True)
class SpecState:
    observed: ObservedState       # abstract observation of concrete DB
    derived: DerivedState         # pure calculations from observed
    environment: EnvironmentState # contract-relevant environment
    history: HistoryState         # interpreted execution trace
    ghost: GhostState             # proof/specification-only state
```

Every field records its **semantic provenance**.  This prevents all
specification-only values from being conflated with values stored in a
database table.

#### Observed state

State obtained from the concrete system (database tables, rows).  This
is NOT ghost state — it is an abstract observation of concrete state.

```python
@dataclass(frozen=True)
class ObservedState:
    accounts: Mapping[AccountId, Account]
    limits: Mapping[str, int]  # transfer limits from a DB table
```

#### Derived state

Pure values calculated from observations.  Convenient for contracts
but need not be stored physically.

#### Environment state

External values relevant to execution: current time, authenticated
principal, configuration, feature flags.

#### History state

The abstract interpretation of the execution trace.  Required for
properties such as idempotency, serializability, at-most-once
processing, no effects after rollback.

#### Genuine ghost state

Proof- or specification-only state that need NOT be recoverable from
the database: initial totals, linearization witnesses, abstract
ownership, proof witnesses.  The implementation must not depend
computationally on genuine ghost fields.

### Contracts — the `Contract` model

Contracts are **external to the implementation**.  They are declared in a
separate file (or directory) and reference an existing implementation by
function reference, not by modifying the implementation's source code.

Two declaration styles are supported:

**Standalone** — for existing (brownfield) code:

```python
# examples/<domain>/contract.py
from specsaver.contract_model import Contract

transfer_contract = Contract(
    TransferService.transfer,          # existing function — never modified
    args_type=TransferArgs,            # explicit Args type, not auto-derived
    feature="transfer.feature",        # the .feature file this belongs to
    when='funds of <amount> are transferred ...',
    observe=TransferProjection().snapshot,  # how to lift DB → SpecState
    requires=[...], ensures=[...], exceptions={...}, invariants=[...],
    ghost_state=TransferGhost, ghost_init=..., ghost_transitions=[...],
    writes={...}, reads={...}, uses={...}, emits={...},
)
```

**Decorator** — for greenfield code:

```python
# examples/<domain>/service.py
from specsaver.contract_model import contract

@contract(args_type=TransferArgs, feature="transfer.feature", ...)
class TransferService:
    def transfer(self, db_path, source_id, target_id, amount):
        ...
```

Both produce an identical `Contract` object.  The `Contract` holds:

| Field           | Purpose                                     |
|-----------------|---------------------------------------------|
| `requires`      | Admissibility predicates `(state, args) → bool` |
| `ensures`       | Transition predicates `(old_s, args, result, new_s) → bool` |
| `exceptions`    | Exception type → condition `(state, args) → bool` |
| `invariants`    | Ambient cross-cutting `(state) → bool` |
| `ghost_state`   | Spec-only type (e.g. `TransferGhost`) |
| `ghost_init`    | `(witness) → ghost_instance` |
| `ghost_transitions` | `(old_g, args, result, new_g) → bool` |
| `observe`       | `(db_connection) → ObservedState` — the projection |
| `writes`/`reads` | Frame conditions |
| `uses`/`emits`  | Side-effect declarations |
| `impl`          | The unmodified implementation function |
| `args_type`     | Explicit frozen dataclass — never derived by position |

The test runner reads `Contract` objects at module level and wires them
to the Gherkin examples.  The implementation is never imported by the
contract — contracts reference the function, not the other way around.

### Organising contracts

A domain may have multiple entry points.  Each gets its own contract file:

```
examples/bank_transfer/
    contract.py    # from .service import TransferService
                   # transfer_contract = Contract(TransferService.transfer, ...)

    another_entry_point/
        contract.py  # contract = Contract(AnotherService.do_something, ...)
```

Or a single `contracts/` directory:

```
examples/bank_transfer/
    contracts/
        transfer.py
        audit.py
        reporting.py
```

Tests and runners discover contracts by importing the module and reading
module-level `Contract` instances.

### Contract predicates

Predicates are regular Python callables (lambdas or named functions) with
canonical signatures.  Implication is expressed via ``implies()``:
``implies(isinstance(result, TransferReceipt), ...)`` ≡ ``receipt → balance
changed``.  See the *Contract Language Specification* for the full type
system.

### Persistent state is not ghost state

State read from a database table (e.g. `transfer_limits`) is
**observed** state, even when only contracts use it.  Genuine ghost
state is initialized or evolved by specification machinery and need
not exist in concrete storage.  The `@ghost` decorator marks genuine
ghost types; observed types use plain dataclasses.

---

## 4. Layer 3 — Example elaboration

An abstract example should produce a `ScenarioWitness`, not merely a
`State`:

```python
@dataclass(frozen=True)
class ScenarioWitness:
    initial_observed_state: ObservedState
    initial_environment: EnvironmentState
    initial_ghost_state: GhostState
    args: Args
```

The Examples row in the Gherkin file describes semantic partitions
(concrete numbers in the simplest case, named classes in the preferred
case).  The witness generator instantiates a concrete
`ScenarioWitness` from the row.

---

## 5. Layer 4 — Concrete implementation

The implementation is a real function that operates on the
`ExecutionContext`:

```python
class ImplementationAdapter(Protocol):
    def execute(self, context: ExecutionContext, args: Args) -> Result:
        ...
```

Key principles:
1. **Injected at test time.**  Contracts never import the implementation.
2. **Operates on ExecutionContext**, not on abstract `SpecState`.
3. **No contract awareness.**  The impl does not check preconditions.
4. **Returns `Result`** (success or error variant).

---

## 6. Layer 5 — Projection and refinement bridge

This is the first-class coupling layer between the concrete execution
world and the abstract specification state.

### Materialization

```python
class ScenarioMaterializer(Protocol):
    def materialize(self, witness: ScenarioWitness) -> ExecutionContext:
        ...
```

Creates the concrete execution world (database, environment, trace
recorder, ghost store) from a scenario witness.

### Specification projection

```python
class SpecificationProjection(Protocol):
    def snapshot(self, context: ExecutionContext) -> SpecState:
        ...
```

Projects the execution context into an immutable `SpecState`.  The
**same** projection must be used before and after execution.  This is
the symmetry requirement (§6 of the Symmetric document).

### The symmetric flow

```python
context = materialize(witness)

# Project the ACTUAL execution world, not the witness
before = snapshot(context)

# Validate materialization agrees with the witness
assert materialization_agreement(witness, before)

# Check invariants on the projected pre-state
check_invariants(before)

# Check admissibility (true caller preconditions)
if not admissibility(before, args):
    return handle_precondition_failure(...)

# Classify which operation case applies
case = classify(before, args)

# Execute the real implementation on the real context
result = implementation.execute(context, args)

# Project the SAME execution world after execution
after = snapshot(context)

# Check transition, frame, invariants for the selected case
check_case(case, before, args, result, after)
check_frame(before, args, result, after)
check_invariants(after)
```

The contracts therefore see two values of the same type produced by
the same interpretation of the same execution world.  The
precondition is checked against the projected database state, not
against the input witness — this prevents silent divergence.

### Coupling relation

The round-trip property `snapshot(materialize(witness))` must agree
with the witness on all declared observable and scenario-ghost
fields.  The general coupling concept is a representation relation:

```
Represents(concrete_execution_world, specification_state)
```

Formally:

```
R(C, S) ∧ Exec(C, a, C', r)  ⇒  ∃ S'. R(C', S') ∧ Post(S, a, r, S')
```

When the projection is functional (`S = α(C)`), the post-state is
`S' = α(C')`.  Testing uses this functional projection.  Formal
verification retains the relational interpretation for non-unique
witnesses and concurrency.

---

## 7. Layer 6 — Evidence consumers

### The generic symmetric runner

```python
def run_scenario(
    contract: OperationContract,
    witness: ScenarioWitness,
    implementation: ImplementationAdapter,
) -> ScenarioResult:
    context = materialize(witness)
    before = contract.projection.snapshot(context)
    contract.check_invariants(before)

    if not contract.admissibility(before, witness.args):
        return handle_precondition_failure(contract, before, witness)

    case = contract.classify(before, witness.args)
    result = implementation.execute(context, witness.args)
    after = contract.projection.snapshot(context)

    contract.check_case(case, before, witness.args, result, after)
    contract.check_frame(before, witness.args, result, after)
    contract.check_invariants(after)

    return ScenarioResult(before, after, result, trace, case)
```

The runner is generic.  Domain-specific code supplies:
- witness generation (from Gherkin Examples rows);
- database materialization;
- database observation (snapshot);
- environment observation;
- trace interpretation;
- ghost initialization;
- implementation adaptation.

### Specification tests — two approaches

**Via pytest-bdd** (reads `.feature` files, matches Gherkin steps to
Python step definitions):

```python
# tests/test_pytest_bdd.py
from pytest_bdd import given, parsers, scenarios, then, when

scenarios("examples/bank_transfer/transfer.feature")

@when(parsers.re(r'funds of (?P<amount>\S+) are transferred ...'))
def when_transfer(amount, source, target, ctx):
    row = build_witness(...)
    ctx["context"] = materializer.materialize(row)
    ...
    result = contract.invoke(svc, ctx["context"].db_path, ctx["args"])
```

No hand-written assertions beyond the Then steps — the contract's
predicates are exercised by the step definitions.  The Gherkin
feature file drives both the BDD runner and the contract verifier.

**Via the specsaver CLI** (one-command check):

```bash
uv run specsaver trace examples.bank_transfer.contracts --verify
uv run specsaver trace examples.bank_transfer.contracts --pre-only
```

`--verify` runs every Examples row through the full symmetric pipeline
(materialise → snapshot → check admissibility → execute → snapshot →
check transitions).  `--pre-only` checks only admissibility + invariants,
requiring no implementation.

**Via generic pytest** (advanced, when custom assertions are needed):

```python
@pytest.mark.parametrize("row", all_rows(), ids=row_id)
def test_scenario(row):
    runner = TransferScenarioRunner()
    passed, message = runner.run(row)
    assert passed, f"Scenario failed: {message}"
```

The `TransferScenarioRunner` bundles all domain wiring (witness builder,
materializer, projection, impl adapter) into one object exported from
the domain package.  Both the CLI and pytest consume it.

---

## 8. Ghost state — the correct classification

| Source | Classification | Example |
|--------|---------------|---------|
| Database table | Observed | `accounts`, `transfer_limits` |
| Calculated from observed | Derived | `total_balance`, `active_account_ids` |
| External runtime | Environment | `current_time`, `principal`, `config` |
| Interpreted trace | History | `logical_events`, `processed_prefix` |
| Specification/proof-only | Ghost | `initial_total`, `linearization_witness`, `logical_owner` |

The `@ghost` decorator marks only the last row.  Persistent
configuration in a database table (like transfer limits) is **observed
state**, not ghost state, even when only contracts reference it.

Genuine ghost state must obey noninterference:

```
concrete/runtime state  → may inform ghost state
ghost state             ↛ may not control production computation
```

---

## 9. Preconditions versus business rejection

Two distinct concepts (§12 of the Symmetric document):

### Caller precondition (admissibility)

A true Hoare-style requirement.  When this fails, the operation is
outside the verified contract and the implementation is not called.

```python
@requires  # admissibility
def well_formed_request(state: SpecState, args: Args) -> bool:
    return args.amount > 0
```

### Business rejection case

A specified behavior.  The implementation IS called and returns an
error result.  The transition postcondition checks that the error
result is returned and state is unchanged.

```python
@case("insufficient-funds")
def insufficient_funds(state: SpecState, args: Args) -> bool:
    return state.observed.accounts[args.source_id].balance < args.amount

@ensures(case="insufficient-funds")
def returns_rejection(old, args, result, new) -> bool:
    return (
        isinstance(result, TransferError)
        and result.code == "INSUFFICIENT_FUNDS"
        and new == old
    )
```

A `rejected` Gherkin example should **execute the implementation**
when rejection is part of the defined business behavior.  The
implementation should be skipped only when the row intentionally
violates a caller obligation (malformed input).

---

## 10. Adding a new feature — step by step

### Step 1: Write the Gherkin

Create `examples/<domain>/transfer.feature` with Rules (for invariants),
Scenario Outlines, and Examples tables (with `outcome` column).

### Step 2: Write the contract

Create `examples/<domain>/contract.py`:

```python
from specsaver.contract_model import Contract

transfer_contract = Contract(
    existing_service.transfer,     # existing function — not modified
    args_type=TransferArgs,        # explicit frozen dataclass
    feature="transfer.feature",
    when='funds of <amount> are transferred ...',
    observe=TransferProjection().snapshot,
    requires=[
        lambda state, args: args.amount > 0,
        lambda state, args: args.source_id in state.observed.accounts,
    ],
    ensures=[
        lambda old_s, args, result, new_s: (
            old_s.derived.total_balance == new_s.derived.total_balance
        ),
        lambda old_s, args, result, new_s: implies(
            isinstance(result, TransferReceipt),
            new_s.observed.accounts[args.source_id].balance
            == old_s.observed.accounts[args.source_id].balance - args.amount,
        ),
    ],
    exceptions={
        InsufficientFundsError: lambda state, args: (
            state.observed.accounts[args.source_id].balance < args.amount
        ),
    },
    invariants=[
        lambda state: all(a.balance >= 0 for a in state.observed.accounts.values()),
    ],
    ghost_state=Ghost, ghost_init=lambda w: Ghost(...), ...
    writes={"source.balance", "target.balance", "audit_log"},
    emits={"audit.transfer_completed", "notification.funds_received"},
)
```

Or use the decorator style on a new implementation class:

```python
@contract(args_type=TransferArgs, feature="transfer.feature", ...)
class TransferService:
    def transfer(self, db_path, source_id, target_id, amount):
        ...
```

### Step 3: Write the implementation

Create `examples/<domain>/service.py`.  The implementation is **never
imported by contracts** — contracts reference the function, not the
other way around.

### Step 4: Write the projection bridge

Create `examples/<domain>/projection.py`:
- `build_witness(row)` — Gherkin columns → ScenarioWitness + Args.
- `TransferMaterializer` — witness → temp SQLite DB.
- `TransferProjection` — DB connection → `SpecState` (the `observe` function).
- `TransferScenarioRunner` — bundles witness, materializer, projection, impl.
  Exported once; consumed by both CLI and tests.

### Step 5: Write BDD step definitions

Create `tests/test_pytest_bdd.py`:

```python
from pytest_bdd import given, parsers, scenarios, when, then

scenarios("examples/<domain>/transfer.feature")

@when(parsers.re(r'funds of (?P<amount>\S+) are transferred ...'))
def when_transfer(amount, source, target, ctx):
    row = build_witness(...)
    context = materializer.materialize(row)
    result = contract.invoke(svc, context.db_path, ctx["args"])
    ...
```

### Step 6: Run

```bash
uv run pytest tests/test_pytest_bdd.py -v     # BDD — reads .feature directly
uv run specsaver trace examples.<domain>.contracts --verify  # CLI
```

Every Examples row is now a test case.  Adding a row to the feature file
adds a test.  Adding a contract adds a check to every row.  No test code
changes needed beyond the step definitions (written once per domain).

### Step 4: Write the projection bridge

Create `examples/<domain>/projection.py`:
- `materialize(witness) → ExecutionContext` — create DB, environment,
  trace recorder, ghost store from the witness.
- `snapshot(context) → SpecState` — project DB + environment + trace +
  ghost into immutable `SpecState`.
- `snapshot` is the **same** function used before and after execution.

### Step 5: Write the witness generator

Create `examples/<domain>/witness.py`:
- `build_witness(row) → ScenarioWitness` — maps Gherkin Examples
  columns to `ScenarioWitness` (initial observed state, environment,
  ghost, args).

### Step 6: Write the test wiring

Create `tests/test_<domain>.py`:
1. `build_witness(row)` — from Examples columns.
2. `impl_adapter` — wraps the real impl as `ImplementationAdapter`.
3. One parametrised test calling `run_scenario`.

### Step 7: Run

```bash
uv run pytest tests/test_<domain>.py -v
```

---

## 11. What is NOT generic (and why)

| Concern | Why it stays domain-specific |
|---------|-------------------------------|
| `SpecState` type | Each domain has different state with different provenance. |
| `Args`/`Result` types | Each operation has different inputs/outputs. |
| `build_witness(row)` | Maps Gherkin columns to witness. Column names are domain-specific. |
| `materialize(witness)` | Creates domain-specific database schema and environment. |
| `snapshot(context)` | Reads domain-specific tables into domain-specific `SpecState`. |
| `impl_adapter` | Bridges impl signature to `ImplementationAdapter`. |
| `fault_injector` | Domain-specific fault simulation. |

Everything else — Gherkin parser, ``Contract`` model, CLI commands
(``trace``, ``render``, ``check``, ``list-contracts``), BDD step
definition framework, validation laws — is generic and lives in
``src/specsaver/``.

---

## 12. Validation laws

The system should automatically test (§20 of the Symmetric document):

- **Projection determinism**: `snapshot(context) == snapshot(context)`
- **Materialization agreement**: `snapshot(materialize(witness))`
  satisfies the witness constraints
- **Stable identity**: same concrete row → same logical identifier
- **Ghost noninterference**: changing proof-only ghost fields must not
  alter concrete execution
- **Derivation correctness**: derived fields equal their definitions
- **Trace consistency**: abstract history is a valid interpretation of
  the recorded concrete trace
- **Post-state symmetry**: `before` and `after` produced by the same
  projection
- **Case coverage**: every admissible state+args selects ≥1 case
- **Case disjointness**: where intended, cases are mutually exclusive

---

## 13. Formal verification path (future)

The same contracts + projection serve formal proof.  The proof
obligation for each operation:

```
Assume:
    Represents(concrete_before, spec_before)
    Invariant(spec_before)
    Admissibility(spec_before, args)
    SelectedCase(spec_before, args)

Prove:
    execution returns an allowed result
    ∃ spec_after. Represents(concrete_after, spec_after)
    ∧ Transition(spec_before, args, result, spec_after)
    ∧ Frame(spec_before, args, result, spec_after)
    ∧ Invariant(spec_after)
```

The testing pipeline samples this commuting diagram on concrete
witnesses.  Formal verification proves it universally.  No changes to
layers 1–5 are needed — the proof layer is a consumer of the same
artifacts.
