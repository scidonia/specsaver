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

### Contracts

Each contract is a pure function with canonical signatures:

| Kind          | Signature                                    |
|---------------|----------------------------------------------|
| Admissibility | `(state: SpecState, args: Args) → bool`     |
| Case condition| `(state: SpecState, args: Args) → bool`     |
| Transition    | `(old_state: SpecState, args: Args, result: Result, new_state: SpecState) → bool` |
| Frame         | `(old_state: SpecState, args: Args, result: Result, new_state: SpecState) → bool` |
| Invariant     | `(state: SpecState) → bool`                 |

These never change.  Ghost state, environment, history — all of it
lives as fields on `SpecState`, not as extra parameters.

Rules:
1. **One contract per `from_gherkin` association.**  No implicit ANDs.
2. **Inline the Gherkin text** in each decorator.
3. **`from_gherkin` must match the feature file exactly.**
4. **No `entry_point`.**  Contracts are grouped by `feature`.
5. **Transitions are organised by operation case**, not by
   self-guarding postconditions.  See §11–12 of the Symmetric document.

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

### Specification tests

One parametrised test per Examples row:

```python
@pytest.mark.parametrize("row", all_rows(), ids=row_id)
def test_scenario(row):
    witness = build_witness(row)
    contract = OperationContract.from_feature(FEATURE_PATH, "Transfer funds")
    run_scenario(contract, witness, impl_adapter)
```

No hand-written assertions.  Adding a row to the feature file adds a
test.  Adding a contract adds a check to every row.

### Other consumers

The same contracts + projection serve:
- **Implementation tests** — run against the real SQLite-backed impl.
- **Trace tests** — verify properties of the recorded execution trace
  (no partial commit, no write after rollback, exactly one
  idempotency record).
- **Runtime monitors** — execute contract predicates as instrumentation
  in production.
- **Formal verification** — generate VCs from the same contract +
  projection, discharge via SMT.

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

Create `examples/<domain>/<domain>.feature` with Rules, Scenario
Outline, and Examples tables (with `outcome` column).

### Step 2: Write the contracts

Create `examples/<domain>/contracts.py`:
1. Define `SpecState` with provenance decomposition (observed,
   derived, environment, history, ghost).
2. Define `Args(Args)`, `Result` variants (success + error).
3. Write admissibility (`@requires`), operation cases (`@case`),
   transitions (`@ensures`), invariants (`@invariant`), frame
   conditions (`@writes`/`@reads`), effects (`@effect`).
4. Each with `from_gherkin` matching the Gherkin step text exactly.

### Step 3: Write the implementation

Create `examples/<domain>/service.py`:
- Operates on `ExecutionContext` (database, environment, trace).
- Returns `Result` (success or error variant).
- Does NOT check admissibility — the contract system does that.

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

Everything else — Gherkin parser, contract registry, scenario
assembler, scenario runner, assertion logic, outcome dispatch,
validation laws — is generic and lives in `src/specsaver/`.

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
