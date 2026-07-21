# Axiomander — Gradual Specification from BDD to Formal Proof

**Status:** Design — v0.1
**Scope:** System unification (naming/repository), effect theory for
database and I/O calls, and the proof ladder from runtime-checked
contracts to Iris-verified contracts.

---

## 1. Vision

**Axiomander** is a single coding system for *gradual specification*:
one contract language, consumed at increasing levels of semantic
strength, so that a team can start with executable BDD scenarios and
end — where it matters — at machine-checked proof, without rewriting
the specification at any rung.

```
Gherkin scenarios          concrete Examples rows drive the system
      │
Runtime contract checking  ScenarioRunner: frames, invariants,
      │                    exceptions, telemetry — on real executions
      │
Semantic frames            writes enforced; preservation generated
      │
Spec consistency           contracts are satisfiable (Iris, no impl)
      │
Sequence verification      multi-call properties proven (Iris)
      │
Model refinement           implementation models proven against specs
```

The contract is the **single source of semantic truth** at every rung.
Nothing on the right may introduce independent semantics; everything
derives from the same `Contract` objects that already drive testing.

Today the rungs exist in two repositories: the contract language,
runtime runner, frame checker, and renderer live in **specsaver**; the
Iris WP calculus, Snakelet language, contract IR, and proof pipeline
live in **axiomander**.  This document designs their unification under
one name — **axiomander** — and the effect theory that connects them.

---

## 2. Naming and repository migration (Requirement A)

The *system* is called axiomander.  The contract language and runtime
(currently specsaver) become its specification layer; the verification
backend (currently axiomander) becomes its proof layer.

### 2.1 Options

**Option 1 — Rename specsaver → axiomander (recommended).**
The contract layer is the system's living front end and its most
actively developed core; renaming its repository preserves GitHub
redirects, issues, and history.  The proof layer is merged in as a
subtree (`backend/`, `coq/`, `py/axiomander/oracle/` →
`axiomander/backend/`).  The old axiomander repository is archived
with a pointer.  PyPI: publish `axiomander`; release a final
`specsaver` shim that depends on `axiomander` and re-exports the API
with a deprecation warning.

**Option 2 — Absorb specsaver into the axiomander repository.**
Keeps the proof layer's build (Coq/dune/opam) in place, but that
repository carries substantial build artefacts and a heavier history;
the contract layer's clean Python-only packaging is the better
foundation for a PyPI-facing system.

**Option 3 — New repository, both archived.**
Cleanest narrative, highest migration cost, loses both histories'
redirects.

**Recommendation: Option 1.**  The specification layer is what users
import first; the proof layer arrives as an optional extra
(`axiomander[proof]` pulls opam/Coq-side tooling).

### 2.2 Target package layout

```
axiomander/
    spec/            — Contract, ExcExit, StateField, logic combinators
    runtime/         — ScenarioRunner, frames, projections, EventLog
    render/          — CLI + mathematical rendering
    lower/           — contract → contract_ir bridge (Z-abstraction)
    backend/
        iris/        — SnakeletIR, proof generation, pipeline
        smt/         — SMT export path
coq/                 — SnakeletLang, SnakeletWp, tactics
examples/            — bank_transfer, inventory (test matrix)
docs/                — this document and the language specification
```

Import compatibility during migration: `specsaver.X` continues to work
via the shim for at least one minor cycle; new code imports
`axiomander.spec` / `axiomander.runtime`.

---

## 3. The effect theory (Requirement B)

Contracts must reason about programs that call databases and emit I/O.
We give those calls a **theory**: an *event-based algebra* with an
initial syntactic reading (what the program asked to happen) and a
**final semantic interpretation** (what observably happened — the
trace).  Contracts quantify over the final interpretation only.

### 3.1 Signatures

Three effect families are in scope for v1:

| Family | Constructors (events) |
|---|---|
| **Logging** | `Log(logger, level, message, fields)` |
| **OpenTelemetry** | `SpanStart(name, attrs, parent)`, `SpanEnd(span, status)`, `Metric(name, value, attrs)` |
| **SQLAlchemy** | `Begin()`, `Execute(stmt, params)`, `Fetch(howmany)`, `Commit()`, `Rollback()` |

An event is a frozen dataclass — exactly the shape already used for
telemetry events in the inventory example.  Each family may be extended
later; the theory is open in the constructors, closed in the semantics.

### 3.2 Initial algebra — the syntax of effects

A program with effects is a chain of constructors terminating in
`Return(v)` — the free algebra over the signature.  The initial
reading is syntax: *what the program asked to happen*.  No semantics
yet; this is the level at which static analyses (coverage, linting,
the contract IR bridge) operate.

### 3.3 Final interpretation — trace semantics

The final reading maps every program to `(result, trace)` where the
trace is the sequence of events it produced.  This is the **final
semantic interpretation**: two programs are observationally equal iff
they produce the same result and the same trace.  Everything a
contract may say is a predicate over this pair — nothing else is
observable, by definition.

Handlers (folds over the initial algebra) produce interpretations:

- **LiveHandler** — performs real effects: Python `logging`, the OTel
  SDK, a real SQLAlchemy `Connection`.  Used in production and in
  integration tests.  Its trace is recorded alongside.
- **StubHandler** — pure, deterministic, in-memory: SQLAlchemy events
  mutate a table model (`dict[str, dict[str, Any]]`), logging/OTel
  events append to the trace, responses come from a witness script.
  This is the materializer's role today, generalized: scenario tests
  run implementations against the stub.
- **ProjectionHandler** — lifts a trace into specification state.
  This *is* the lifting α from the database-theory discussion: the
  products map is the stub's table state; the telemetry logs are the
  trace filtered by constructor family.  **Determinism requirement:**
  projections must be order-insensitive for maps and order-explicit
  (`ORDER BY`-equivalent) for sequences — stated once in the theory,
  not rediscovered per domain.

### 3.4 What contracts become under the theory

The theory unifies three things we already built:

- **Observed state** = stub state ∪ trace projections.  The
  `EventLog` in today's examples is precisely the logging family's
  trace; the SQLAlchemy family joins it as first-class events.
- **Frame conditions = effect permissions.**  A `writes` set is a
  statement about which constructors may appear in this operation's
  trace segment, and which state cells the SQLAlchemy events may
  touch.  Per-exit `writes` are per-exit effect permissions — the
  runtime frame checker already enforces exactly this; the theory
  gives it denotation.
- **Telemetry clauses = trace predicates.**  `extends_by_one` is a
  predicate on trace extension; edge-triggered alerts are predicates
  on trace+state jointly.  Both already exist; the theory names their
  domain.

OpenTelemetry's nondeterminism (durations, timestamps, span IDs) is
quotiented by the final interpretation: contracts see *logical* spans
(name, attributes, status, parent edge) only.  The projection drops
timing by construction, so specs stay deterministic.

### 3.5 Refinement between stub and live

The stub is sound for testing iff its traces refine the live
handler's possible traces: every stub producible trace is a live
possibility, modulo the parameters the witness controls.  For
SQLAlchemy v1 this is enforced structurally — the stub implements the
same event constructors against a table model whose transitions match
SQL semantics for the covered statement classes (`INSERT`, `UPDATE`,
`SELECT` with equality predicates, `BEGIN/COMMIT/ROLLBACK`).  The
ladder: contracts proven against the stub semantics hold of the real
system insofar as the refinement is maintained — and the runtime
runner continuously validates the real side against the same
contracts.

---

## 4. The proof ladder

### 4.0 Proof style: obligation dumping

We are deliberately **liberal with proof obligations**.  The style is
verification-condition generation, not tactical choreography: compute
*every* obligation a contract gives rise to, emit them as independent
Coq lemmas over an axiomatized state model, and throw the whole set at
a theorem prover to see how it does.  No ANF normalization, no staged
tactic scripts, no WP plumbing — one `.v` file of lemmas, a portfolio
of automation (`lia`, `congruence`, `sauto`, SMT via SMTCoq) with a
per-lemma timeout, and a report.

**Prove *or refute*.**  Every obligation is attacked from both sides.
A failed proof attempt is ambiguous — the spec may be wrong, or the
automation merely weak — so the pipeline also tries to **disprove**:
negate the obligation and hunt for a concrete counterexample (an SMT
model of the negation where the fragment allows; LLM-assisted
counterexample search otherwise — §4.0.1).  The scoreboard is
three-valued: **PROVED / DISPROVED / UNKNOWN**, per obligation.  A
DISPROVED row is a *spec bug with a witness* — the highest-value
output the pipeline can produce; an UNKNOWN row routes to escalation
(SMT slot, then staged proofs) only if the obligation matters.

Elaborate proof engineering (staged scripts, Iris WP, separation
reasoning) is the *escalation path*, reserved for obligations that
fail automation and matter — not the default.  This matches the
project's evidence-driven discipline everywhere else: try the cheap
thing, measure precisely, invest only where the measurement says to.

#### 4.0.1 LLM-assisted disproof and the evidence payload

For obligations outside SMT-friendly fragments (event logs, record
state, uninterpreted helpers), an LLM oracle hunts for
counterexamples.  The prompting contract is strict:

- **Input**: the obligation, the axiomatized state model, the
  relevant contract clauses in rendered form, and the domain's
  Gherkin rows as seed witnesses.
- **Output**: a *concrete candidate counterexample* — before-state,
  args, result, after-state as literal values, plus the LLM's
  natural-language reasoning: which clause fails and why.

**Nothing is believed unvalidated.**  A candidate becomes a DISPROVED
verdict only after mechanical confirmation, and confirmation is cheap
because contracts are executable: run the actual clause lambdas on
the candidate values (`requires(before, args) ∧ invariant(before) ∧
¬ensures(before, args, result, after)` must all evaluate literally).

A DISPROVED verdict carries a full **evidence payload**:

1. **The witness** — the concrete assignment, rendered as values.
2. **The failing clause** — which conjunct of which obligation, with
   its evaluated left- and right-hand sides.
3. **The reasoning** — the LLM's explanation, clearly labelled as
   advisory; the witness is the evidence, the reasoning is commentary.
4. **A materialized scenario** — the witness converts to a Gherkin
   Examples row (same schema the runner already consumes), so the
   counterexample can be *executed against the real implementation*.
   If the real impl satisfies the contract on that row, the
   counterexample indicted the **specification** (or the abstract
   model); if the impl violates too, it indicted the
   **implementation**.  Disproof thus separates spec bugs from impl
   bugs — the same tamper-loop we run by hand today, automated.

This dual use of the LLM is symmetric with its use as a proof oracle
elsewhere in the pipeline: in both directions the LLM proposes
*artifacts* (proof scripts, counterexamples) and the system disposes
mechanically.

**The obligation inventory** (each contract generates all of these):

| # | Obligation | Statement sketch |
|---|---|---|
| O1 | Admissibility sanity | `∃ state args. requires ∧ invariant(state)` — the spec isn't vacuous |
| O2 | Spec consistency | `requires ∧ invariant(before) ⇒ ∃ result after. ensures ∧ invariant(after)` |
| O3 | Exception consistency | `requires ∧ when_i ⇒ ∃ exc after. ensures_i(exc) ∧ invariant(after)` per exit |
| O4 | Exit coverage | declared exits cover the failure space; `when` guards are disjoint where required |
| O5 | Invariant preservation | `requires ∧ invariant(before) ∧ ensures ⇒ invariant(after)` — the classic |
| O6 | Derived soundness | ensures + frame entail the declared `derives` values (derived-consistency as theorem, not just runtime check) |
| O7 | Sequence lemmas | relational compositions: e.g. `reserve; release ⇒ state unchanged` |

**The state model is axiomatized, not lowered.**  Maps are
`string → option row` (or total functions with a default), event logs
are `list event` with `extends_by_one` defined inductively, derived
fields are functions, and the frame contributes *facts*: everything
outside `writes` is equal — generated from the same path language the
runtime checker uses, so runtime and proof read one footprint
definition.  Frame-generated preservation clauses are assumptions in
the obligations, never goals.

### 4.1 Phases

**Phase 0 — Coverage spike (½ day).**  Run the proof layer's
`ContractLinter` over every predicate in both examples.  Output: a
coverage table (which clauses land in the compilable fragment vs.
need the phase-3 value model).  Evidence gates everything after.

**Phase 1 — The Z-abstraction bridge (`axiomander/lower/`).**
Flatten state paths to Z variables — note that frame write-paths
(`state.products[sku].reserved`) are *already* flattened names — then
lower clause lambdas → `contract_ir` → Coq Props via
`contract_ir_iris`.  Deliverable: `(pre, post)` Prop pairs per
contract with a documented name mapping.

**Phase 2 — Obligation emission + first dump.**  Generate the
obligation inventory (O1–O6) for both example domains as a single
`.v` file per domain and run the portfolio.  This replaces staged
proof generation entirely for consistency-style properties: the
obligations are first-order lemmas over the axiomatized model, and
the interesting output is the *scoreboard* — how far brute automation
gets before any proof engineering.  Failures route to the SMT slot
first, staged proofs only if the SMT slot also fails and the
obligation matters.

**Phase 3 — Effect theory v1.**  Event algebra + three handlers;
`EventLog` becomes the logging-family trace; SQLAlchemy stub replaces
raw sqlite in materializers; OTel events join the observed trace with
timing quotiented.  Contracts quantify over the unified final trace.
The algebra also *names* the events that the O-series state model
axiomatizes — one signature, two consumers (runtime and proof).

**Phase 4 — Sequence verification (O7).**  Multi-call properties as
relational compositions over the same axiomatized model
(`reserve → release → restock`), emitted as more obligations and
dumped.  Opaque-call WP (`wp_call` chains) remains the escalation
path for sequences automation can't close.  Closes the single-call
limitation of the runtime runner.

**Phase 5 — Model refinement.**  Hand-lowered service skeletons as
`FunDef`s proven against their `FunSpec`s — this is the one phase
where WP-style reasoning is structural, not optional, and where
axiomander's staged machinery earns its keep from day one.  The real
SQLAlchemy implementation stays covered by the runtime runner: proof
covers the arithmetic core, testing covers real effects.  Later:
generate skeletons semi-automatically from service source by mapping
SQLAlchemy calls onto the event algebra — the theory's payoff, since
the algebra fixes exactly what a call *means*.

**Phase 6 (deferred).**  Full value model in SnakeletLang (lists for
traces, records for rows); frame conditions as separation-logic
footprints — the per-exit-writes ↔ multi-postconditions correspondence
made formal.

---

## 5. What already exists (do not rebuild)

| Asset | Location | Role in the plan |
|---|---|---|
| `Contract`, `ExcExit`, semantic frames, generic `ScenarioRunner` | specsaver `src/` | Rungs 1–3, done |
| `extends_by_one`, telemetry projection, multi-op inventory | specsaver `examples/` | Evidence base + test matrix for the theory |
| `contract_ir` + `ContractLinter` | axiomander `py/…/oracle/` | The contract AST — single source of truth; do not fork it |
| `contract_ir_iris` | axiomander `py/…/oracle/` | contract_ir → Coq Props (Z-fragment) — the obligation emitter's backend |
| `smt_export` | axiomander `py/…/oracle/` | First escalation for automation-resistant obligations |
| `langgraph_oracle`, `advisor` | axiomander `py/…/oracle/` | LLM oracle infrastructure — reused for the disproof prompting channel |
| SnakeletLang/Wp/Tactics | axiomander `coq/` | Escalation path: WP, opaque calls, staged tactics — used where dumping fails, and structurally in Phase 5 |
| `iris_proof_gen`, `iris_pipeline` | axiomander `py/…/oracle/` | Escalation path: staged `.v` generation for hard obligations |

---

## 6. Risks and open questions

1. **Lambda-shape coverage** of existing contracts vs. the linter's
   vocabulary — gated by Phase 0.
2. **Automation coverage is unknown until the first dump.**  The
   obligation-dumping style deliberately measures before investing;
   the risk is not failure but *silent* failure modes — mitigated by
   the per-obligation PROVED/UNPROVED scoreboard being the primary
   output, never a boolean.
3. **Diagnosability trade-off.**  A failed staged script says which
   stage failed; a failed `sauto` says nothing.  Obligations that
   matter and fail get escalated to the staged path, where the script
   *is* the trace.  Disproof is the compensating diagnostic: a
   DISPROVED verdict comes with witness, failing clause, and a
   materialized scenario row.
4. **LLM-hallucinated counterexamples.**  Mitigated structurally:
   no candidate becomes a verdict without mechanical validation
   against the executable contract; the LLM's reasoning is always
   labelled advisory.
4. **Axiomatized-model drift.**  The Coq state model and the runtime
   projection must not diverge — mitigated by generating both from
   one footprint/path definition (the frame write-paths).
5. **Stub/live refinement for SQLAlchemy** — v1 restricts covered
   statement classes; anything outside fails loudly at the handler,
   never silently.
6. **OTel trace correlation** across threads/tasks is out of scope
   for v1; the theory covers synchronous single-thread emission.
7. **Name availability** — `axiomander` on PyPI must be confirmed
   before the rename lands.
8. **Repository history** — merging the proof layer as a subtree
   preserves blame; a plain copy loses it.  Subtree merge preferred.

---

## 7. Summary

One system, one name — **axiomander** — one contract language at every
rung from Gherkin rows to mechanical proof.  The effect theory
supplies the semantic bridge: database and I/O calls are events in an
algebra, programs fold to traces, contracts quantify over the final
trace — starting with logging, OpenTelemetry, and SQLAlchemy.  And the
proof side starts humble: dump every obligation the contracts imply at
a theorem prover, read the scoreboard, and reserve elaborate proof
engineering for the obligations that earn it.
