# Symmetric Database State in Specification-Driven Testing

## Design recommendation for the specification, testing, and verification pipeline

This document refines the current specification-driven testing architecture to resolve a central requirement:

> The concrete database state used by the implementation must be fed into preconditions and postconditions through the same semantic path, while still allowing abstract state, derived state, execution history, and genuine ghost state to participate in contracts.

The required symmetry is:

```text
Concrete execution world before
        |
        | specification projection
        v
Contract pre-state
        |
        | check preconditions
        v
Execute the real implementation
        |
        v
Concrete execution world after
        |
        | the same specification projection
        v
Contract post-state
        |
        | check postconditions, frames, and invariants
        v
Result
```

The central recommendation is to replace the narrow concept:

```python
load_state(database) -> State
```

with the more general concept:

```python
snapshot(execution_context) -> SpecState
```

`SpecState` is an immutable contract-facing snapshot assembled from all semantically relevant parts of the execution world.

---

## 1. Objective

The pipeline should support the following progression without introducing independent or drifting specifications:

```text
Verbal specification
    ↓
Formal contract specification
    ↓
Specification validation and example generation
    ↓
Concrete implementation
    ↓
Implementation contract testing
    ↓
Formal verification
```

The same contract predicates should serve as the semantic authority for:

- Gherkin rules and scenarios;
- abstract example classes;
- generated specification tests;
- tests against the real implementation;
- runtime contract monitors where appropriate;
- formal proof obligations.

The database must not be treated merely as incidental test setup. It is part of the concrete execution world whose abstract interpretation supplies both the pre-state and post-state of the contract.

---

## 2. The apparent conflict

Two requirements appear to conflict.

First, contracts must be abstract and mathematical:

```python
Pre(spec_state, args) -> bool

Post(
    old_spec_state,
    args,
    result,
    new_spec_state,
) -> bool
```

Second, the implementation operates on a real database:

```python
implementation(database, args) -> result
```

A naïve architecture resolves this by constructing an abstract `State` before the test, materializing it into a database, executing the implementation, and then loading a new abstract `State`.

That is useful, but incomplete. It creates several problems:

1. It may check the precondition against the originally generated object rather than the database state on which the implementation actually executes.
2. It may misclassify persistent configuration or database records as ghost state.
3. It assumes all contract state is recoverable from the database.
4. It treats `load_state` as the complete coupling invariant.
5. It does not naturally represent history, environment, authority, nondeterminism, or proof-only state.
6. It makes it difficult to use exactly the same semantic interface for testing and formal verification.

The solution is to distinguish the concrete execution world from its contract-facing projection.

---

## 3. Core concept: the execution context

The implementation executes within an `ExecutionContext`.

```python
@dataclass
class ExecutionContext:
    database: DatabaseSession
    environment: RuntimeEnvironment
    trace: EventRecorder
    ghost: GhostStore
```

The exact fields may differ by domain, but the conceptual categories should remain stable.

### 3.1 Database

The concrete persistent state used by the implementation:

- tables;
- rows;
- transactions;
- indexes;
- stored configuration;
- audit records;
- idempotency records;
- concrete version data.

### 3.2 Environment

External values relevant to execution:

- current time;
- authenticated principal;
- tenant;
- feature flags;
- configuration;
- random source;
- generated identifiers;
- network or queue responses.

### 3.3 Trace

A record of semantically relevant effects:

- reads;
- writes;
- inserts;
- deletes;
- commits;
- rollbacks;
- external calls;
- emitted messages;
- logical operation boundaries.

### 3.4 Ghost store

State maintained by the specification or verification machinery, not by ordinary implementation code:

- initial snapshots;
- abstract histories;
- logical ownership;
- proof witnesses;
- model-only identifiers;
- progress measures;
- relations between concrete and logical operations.

The implementation should not be permitted to depend computationally on genuine ghost fields.

---

## 4. Core concept: the specification state

The state visible to contracts is an immutable specification snapshot.

```python
@dataclass(frozen=True)
class SpecState:
    observed: ObservedState
    derived: DerivedState
    environment: EnvironmentState
    history: HistoryState
    ghost: GhostState
```

The exact decomposition may be represented with nested dataclasses or flattened fields. The important requirement is that every field records its semantic provenance.

### 4.1 Observed state

State obtained from the concrete system:

```python
@dataclass(frozen=True)
class ObservedState:
    accounts: Mapping[AccountId, Account]
    transfers: Mapping[TransferId, Transfer]
    idempotency_records: Mapping[IdempotencyKey, TransferId]
```

This is not ghost state. It is an abstract observation of concrete state.

### 4.2 Derived state

Pure values calculated from observations:

```python
@dataclass(frozen=True)
class DerivedState:
    total_balance: Money
    active_account_ids: frozenset[AccountId]
```

Derived state is convenient for contracts but need not be stored physically.

### 4.3 Environment state

The contract-relevant environment:

```python
@dataclass(frozen=True)
class EnvironmentState:
    current_time: datetime
    principal: Principal
    configuration: TransferConfiguration
```

### 4.4 History state

The abstract interpretation of the execution trace:

```python
@dataclass(frozen=True)
class HistoryState:
    logical_events: tuple[LogicalEvent, ...]
```

History is required for properties such as:

- idempotency;
- serializability;
- at-most-once processing;
- no effects after rollback;
- monotone version progression;
- eventual event publication.

### 4.5 Genuine ghost state

Proof- or specification-only state:

```python
@dataclass(frozen=True)
class GhostState:
    initial_total: Money
    request_meanings: Mapping[IdempotencyKey, LogicalRequest]
    logical_owner: Mapping[ShardId, WorkerId]
```

Unlike observed state, genuine ghost state need not be recoverable from the database.

---

## 5. The specification projection

A single projection constructs the contract-facing state from the execution context:

```python
def snapshot(context: ExecutionContext) -> SpecState:
    observed = observe_database(context.database)
    environment = observe_environment(context.environment)
    history = interpret_trace(context.trace.snapshot(), context.ghost)
    derived = derive_state(observed, environment, history)
    ghost = context.ghost.snapshot()

    return SpecState(
        observed=observed,
        derived=derived,
        environment=environment,
        history=history,
        ghost=ghost,
    )
```

The same function must be used before and after execution.

This gives the required symmetry:

```python
before = snapshot(context)

check_preconditions(before, args)

result = implementation.execute(context, args)

after = snapshot(context)

check_postconditions(before, args, result, after)
```

The contracts therefore see two values of the same type produced by the same interpretation.

---

## 6. Symmetry requirement

The architecture should explicitly guarantee the following.

### 6.1 Same execution context

The pre-state must be projected from the exact context on which the implementation will execute.

Do not check the precondition only against the input object used to create the database.

Correct:

```python
context = materialize(witness)
before = snapshot(context)
assert contract.pre(before, witness.args)

result = implementation.execute(context, witness.args)
after = snapshot(context)
assert contract.post(before, witness.args, result, after)
```

Incorrect:

```python
assert contract.pre(witness.abstract_state, witness.args)
context = materialize(witness)
result = implementation.execute(context, witness.args)
```

The incorrect version permits the generated abstract state and the actual database state to diverge silently.

### 6.2 Same projection

Pre-state and post-state must be obtained with the same projection definition.

```text
before = snapshot(context_before)
after  = snapshot(context_after)
```

There must not be one hand-written pre-state loader and a separate post-state interpretation.

### 6.3 Stable logical identity

Entities must retain stable logical identities across snapshots:

```python
AccountId
TransferId
RequestId
```

This permits meaningful relational contracts:

```python
after.observed.accounts[args.source].balance == (
    before.observed.accounts[args.source].balance - args.amount
)
```

### 6.4 Immutable snapshots

`before` and `after` should be immutable values.

The implementation must not mutate the contract pre-state object. It mutates only the concrete execution world.

---

## 7. State provenance

Every specification field should be classified by source.

A recommended declaration system is:

```python
@observed
def accounts(database) -> Mapping[AccountId, Account]:
    ...

@derived
def total_balance(observed: ObservedState) -> Money:
    ...

@environment
def current_time(runtime: RuntimeEnvironment) -> datetime:
    ...

@history
def logical_history(trace: EventTrace, ghost: GhostStore) -> HistoryState:
    ...

@ghost(source="scenario")
def initial_total(ghost: GhostStore) -> Money:
    ...

@ghost(source="proof-only")
def serialization_witness(...) -> SerializationOrder:
    ...
```

Recommended ghost source categories:

- `scenario`: introduced by the scenario or example witness;
- `derived`: logically derived but retained as auxiliary state;
- `transition`: evolved by abstract operation semantics;
- `history`: obtained by interpreting traces;
- `proof-only`: available only to formal verification;
- `authority`: records logical ownership or permission.

This prevents all specification-only values from being conflated with values stored in a database table.

---

## 8. Persistent state is not automatically ghost state

The following is concrete observable state:

```python
limits = database.query("SELECT ... FROM transfer_limits")
```

Even when it is used only by contracts, it is still persistent implementation or configuration state.

The following may be genuine ghost state:

```python
initial_total
logical_linearization_order
abstract_owner
processed_prefix
simulation_witness
```

The distinction matters because genuine ghost state must obey noninterference:

```text
concrete/runtime state  → may inform ghost state
ghost state             ↛ may not control production computation
```

Generated runtime monitors may execute contract predicates, but these monitors are instrumentation, not ordinary production dependencies on ghost state.

---

## 9. Scenario witnesses

An abstract example should produce a `ScenarioWitness`, not merely a `State`.

```python
@dataclass(frozen=True)
class ScenarioWitness:
    initial_observed_state: ObservedState
    initial_environment: EnvironmentState
    initial_ghost_state: GhostState
    args: Args
```

Materialization creates the execution world:

```python
def materialize(witness: ScenarioWitness) -> ExecutionContext:
    database = create_database(witness.initial_observed_state)
    environment = create_environment(witness.initial_environment)
    ghost = GhostStore.from_state(witness.initial_ghost_state)

    return ExecutionContext(
        database=database,
        environment=environment,
        trace=EventRecorder(),
        ghost=ghost,
    )
```

After materialization, the harness must re-project the state:

```python
context = materialize(witness)
before = snapshot(context)
```

This checks that the generated witness, concrete materialization, and contract projection agree.

---

## 10. Abstract example classes

Gherkin examples should preferably describe semantic partitions rather than arbitrary concrete numbers.

Preferred:

```gherkin
Examples:
  | state_class        | amount_class    | request_class |
  | minimally_funded   | exact_balance   | fresh         |
  | ordinarily_funded  | strict_interior | fresh         |
  | previously_applied | repeated        | completed     |
```

The row elaborates to constraints:

```python
def example_constraints(row) -> Predicate[ScenarioVariables]:
    ...
```

The system then generates a witness:

```python
def instantiate(
    constraints: Predicate[ScenarioVariables],
) -> ScenarioWitness:
    ...
```

This establishes the hierarchy:

```text
Contract
    universal semantic relation

Example class
    named constrained region of the contract domain

Scenario witness
    one concrete inhabitant

Execution context
    materialized world used by the implementation

SpecState
    projection of that exact execution world
```

---

## 11. Operation contracts

A contract should represent explicit operation cases.

```python
@dataclass(frozen=True)
class OperationCase:
    name: str
    condition: Predicate
    result_shape: Predicate
    transition: Relation
```

```python
@dataclass(frozen=True)
class OperationContract:
    admissibility: Predicate
    cases: tuple[OperationCase, ...]
    frame: Relation
    invariants: tuple[Predicate, ...]
    history_properties: tuple[Predicate, ...]
    projection: SpecificationProjection
```

Recommended signatures:

```python
Admissibility(
    state: SpecState,
    args: Args,
) -> bool
```

```python
CaseCondition(
    state: SpecState,
    args: Args,
) -> bool
```

```python
Transition(
    old_state: SpecState,
    args: Args,
    result: Result,
    new_state: SpecState,
) -> bool
```

```python
Frame(
    old_state: SpecState,
    args: Args,
    result: Result,
    new_state: SpecState,
) -> bool
```

This is preferable to postconditions that silently return `True` for unrelated result types.

---

## 12. Preconditions versus specified rejection

The architecture must distinguish two concepts.

### 12.1 Caller precondition

A true Hoare-style requirement:

```python
@requires
def well_formed_request(state, args) -> bool:
    ...
```

When this fails, the operation is outside the verified contract.

### 12.2 Business rejection case

A specified behavior:

```python
@case("insufficient-funds")
def insufficient_funds(state, args) -> bool:
    ...
```

```python
@ensures(case="insufficient-funds")
def returns_rejection(old, args, result, new) -> bool:
    return (
        isinstance(result, TransferError)
        and result.code == "INSUFFICIENT_FUNDS"
        and new == old
    )
```

A rejected Gherkin example should execute the implementation when rejection is part of the defined business behavior.

The implementation should be skipped only when the row intentionally violates a caller obligation.

---

## 13. Generic symmetric runner

The scenario runner should follow this structure:

```python
def run_scenario(
    contract: OperationContract,
    witness: ScenarioWitness,
    implementation: ImplementationAdapter,
) -> ScenarioResult:
    context = materialize(witness)

    # Project the actual execution world.
    before = contract.projection.snapshot(context)

    # Validate that materialization produced an admissible state.
    contract.check_invariants(before)

    if not contract.admissibility(before, witness.args):
        return handle_caller_precondition_failure(
            contract,
            before,
            witness,
        )

    case = contract.classify(before, witness.args)

    result = implementation.execute(
        context,
        witness.args,
    )

    # Project the same execution world after the real implementation.
    after = contract.projection.snapshot(context)

    contract.check_case(
        case,
        before,
        witness.args,
        result,
        after,
    )

    contract.check_frame(
        before,
        witness.args,
        result,
        after,
    )

    contract.check_invariants(after)

    return ScenarioResult(
        before=before,
        after=after,
        result=result,
        trace=context.trace.snapshot(),
        case=case,
    )
```

This runner is generic. Domain-specific code supplies:

- witness generation;
- database materialization;
- database observation;
- environment observation;
- trace interpretation;
- ghost initialization;
- implementation adaptation.

---

## 14. Database effects and execution traces

Post-hoc database snapshots are necessary, but some properties require effect traces.

A recommended database effect interface is:

```python
class DatabaseEffects(Protocol):
    def read(self, table, key): ...
    def insert(self, table, key, value): ...
    def update(self, table, key, changes): ...
    def delete(self, table, key): ...
    def commit(self): ...
    def rollback(self): ...
```

Different interpreters can support the pipeline:

```text
Operation implementation
        |
        +-- production SQL interpreter
        |
        +-- traced SQL interpreter
        |
        +-- abstract model interpreter
        |
        +-- symbolic verification interpreter
```

The traced interpreter permits properties such as:

- no partial commit;
- no write after rollback;
- exactly one idempotency record inserted;
- account rows updated within one transaction;
- no unrelated rows modified.

The symbolic interpreter can later generate verification conditions from the same effect semantics.

---

## 15. Coupling relation

The fixture round-trip property remains useful:

```python
snapshot(materialize(witness))
```

should agree with the witness on all declared observable and scenario-ghost fields.

However, the formal coupling concept is not merely:

```python
load_state(create_db(state)) == state
```

The general concept is a representation relation:

```text
Represents(concrete_execution_world, specification_state)
```

Formally:

\[
R(C,S)
\land
Exec(C,a,C',r)
\Rightarrow
\exists S'.
\;
R(C',S')
\land
Post(S,a,r,S').
\]

When the projection is functional:

\[
S = \alpha(C),
\]

the post-state can be chosen as:

\[
S' = \alpha(C').
\]

Testing normally uses this functional projection.

Formal verification should retain the more general relational interpretation because:

- several concrete states may represent the same abstract state;
- some concrete details may be irrelevant;
- some logical witnesses are non-unique;
- some proof-only state is not observable;
- concurrency may require existential abstract histories or linearization points.

---

## 16. Formal verification path

Formal verification should consume the same operation contracts and projection specification.

Recommended lowering:

```text
Python implementation
    ↓
PyIR
    ↓
effectful database IR
    ↓
symbolic execution or weakest-precondition calculation
    ↓
verification conditions
```

Database primitives become seams with explicit contracts:

```python
@opaque
@contract(
    requires=...,
    ensures=...,
    effects=...,
)
def update_account_balance(...):
    ...
```

The proof obligation for an operation is:

```text
Assume:
    Represents(concrete_before, spec_before)
    Invariant(spec_before)
    Admissibility(spec_before, args)
    SelectedCase(spec_before, args)

Prove:
    execution returns an allowed result
    there exists a corresponding spec_after
    Represents(concrete_after, spec_after)
    Transition(spec_before, args, result, spec_after)
    Frame(spec_before, args, result, spec_after)
    Invariant(spec_after)
```

The testing pipeline samples this commuting diagram on concrete witnesses. Formal verification proves it universally.

---

## 17. Recommended revision to the current architecture

Replace the current five-layer account:

```text
Gherkin
Contract module
Implementation
Fixtures
Auto-derived tests
```

with the following six-layer semantic architecture:

```text
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

The projection and refinement bridge is a first-class layer, not merely a fixture utility.

---

## 18. Required changes to terminology

### Replace

> Ghost state is just a field on State populated by `load_state`.

### With

> Contract-facing state may contain observed, derived, environmental, historical, and ghost components. Observed fields come from the concrete system; derived fields are calculated from observations; history fields come from trace interpretation; genuine ghost fields are initialized or evolved by specification machinery and need not exist in concrete storage.

### Replace

```python
load_state(db) -> State
```

### With

```python
snapshot(context) -> SpecState
```

### Replace

> The fixture is the coupling invariant.

### With

> The materializer and projection implement an executable instance of the concrete-to-abstract refinement bridge. The general coupling invariant is a representation relation between execution worlds and specification states.

---

## 19. Required framework abstractions

The framework should provide interfaces resembling:

```python
class SpecificationProjection(Protocol):
    def snapshot(self, context: ExecutionContext) -> SpecState:
        ...
```

```python
class ScenarioMaterializer(Protocol):
    def materialize(
        self,
        witness: ScenarioWitness,
    ) -> ExecutionContext:
        ...
```

```python
class WitnessGenerator(Protocol):
    def instantiate(
        self,
        example_class: ExampleClass,
    ) -> ScenarioWitness:
        ...
```

```python
class ImplementationAdapter(Protocol):
    def execute(
        self,
        context: ExecutionContext,
        args: Args,
    ) -> Result:
        ...
```

```python
class TraceInterpreter(Protocol):
    def interpret(
        self,
        trace: EventTrace,
        ghost: GhostStore,
    ) -> HistoryState:
        ...
```

The runner should depend only on these interfaces and on `OperationContract`.

---

## 20. Validation laws

The system should automatically test the following laws.

### Projection determinism

For a stable execution context:

```python
snapshot(context) == snapshot(context)
```

excluding explicitly nondeterministic environmental observations, which must be frozen in the context.

### Materialization agreement

```python
projected = snapshot(materialize(witness))
```

must satisfy the witness constraints.

### Stable identity

The same concrete row maps to the same logical identifier across snapshots.

### Ghost noninterference

Changing proof-only ghost fields must not alter concrete execution behavior.

### Derivation correctness

Derived fields must equal their definitions over observed state.

### Trace consistency

The abstract history must be a valid interpretation of the recorded concrete trace.

### Post-state symmetry

Both `before` and `after` must be produced by the same projection version and schema.

### Case coverage

Every admissible state and argument tuple should select at least one operation case.

### Case disjointness

Where intended, operation cases should be mutually exclusive.

---

## 21. Final recommendation

Adopt the following semantic invariant for the entire framework:

> Contracts never reason directly over test-construction objects or raw database handles. They reason over immutable `SpecState` snapshots. Every snapshot is produced from the exact execution context used by the implementation, through one declared specification projection. The projection combines observed database state, external environment, derived values, interpreted history, and genuine ghost state. The same projection is applied before and after execution.

This squares the circle:

- the database state is genuinely fed into preconditions and postconditions;
- the implementation runs on the same world that was projected for the precondition;
- the contract remains abstract;
- ghost state remains logically distinct from persistent state;
- examples can be generated abstractly and then checked after materialization;
- testing and verification consume the same semantic contract;
- the formal refinement obligation remains visible.

The resulting commuting structure is:

```text
ScenarioWitness
      |
      | materialize
      v
Concrete execution world C₀
      |
      | snapshot
      v
Specification state S₀
      |
      | Pre / case selection
      v
Implementation execution
      |
      v
Concrete execution world C₁
      |
      | same snapshot
      v
Specification state S₁
      |
      | Post / frame / invariant
      v
Evidence
```

That should be treated as the canonical architecture for database-backed specification-driven testing and verification.
