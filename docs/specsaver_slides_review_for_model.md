# Review and Revision Brief: Specsaver / Vericoding Slides

## Purpose of this review

Revise the slide deck so that it works as an explainer for competent Python programmers who have little or no prior exposure to formal verification, proof assistants, design-by-contract, or vericoding.

The current deck is technically strong and internally coherent, but it explains Specsaver from the inside out. It introduces the architecture, terminology, and proof machinery before establishing the practical problem in terms familiar to Python developers. The revision should reverse that order.

The revised deck should make the audience understand, in sequence:

1. what problem Specsaver solves;
2. how it relates to tools they already know;
3. what a contract looks like in ordinary Python terms;
4. how the same contract supports testing, runtime checking, AI-guided implementation, and proof;
5. why the additional machinery is valuable;
6. what has already been implemented and proved.

---

# Executive assessment

The strongest parts of the current deck are:

- the concrete SQLAlchemy example;
- the corresponding contract;
- the idea that one specification is used for both testing and proof;
- the explicit read/write frame;
- the lowering pipeline;
- the final proof status.

The weakest parts are:

- the opening is framed as a critique of “vibecoding” before the audience has been shown a concrete problem;
- the deck assumes familiarity with terms such as admissibility, semantic frame, ghost state, commuting diagram, lowering, proof obligation, and conformance regime;
- the central practical value proposition is not stated early enough;
- the deck contains too many architectural abstractions before the audience has seen a complete end-to-end example;
- the distinction between testing evidence and proof evidence is asserted rather than carefully explained;
- the audience is not shown how Specsaver relates to pytest, Hypothesis, type checking, or ordinary Python development.

The current deck is well suited to a formal methods or verification audience. It is not yet well calibrated for general Python programmers.

---

# Primary revision principle

## Explain the user problem before the verification machinery

The deck should begin with failures Python programmers recognise:

- a test suite passes, but an untested case fails in production;
- an AI rewrites code and preserves syntax but changes behaviour;
- a refactor changes which database rows or fields are modified;
- requirements live separately in tests, tickets, comments, and memory;
- regenerated code has no persistent, machine-checkable statement of intent.

Then introduce Specsaver as the attempt to make behavioural intent durable and executable.

A better opening thesis is:

> Every Python project already has a specification. It is usually scattered across tests, comments, tickets, and people’s heads. Specsaver puts that specification into one executable artifact that can drive testing, checking, and proof.

This is more credible and less adversarial than opening with “vibecoding leaves code and hope.”

---

# Recommended narrative structure

## Section 1: The problem Python developers already have

Start with a small Python example and a familiar failure mode.

Suggested slide sequence:

### Slide 1 — AI can regenerate code, but not intent

Show a short Python function and a one-line behavioural requirement.

Message:

- code is easy to regenerate;
- intended behaviour is not;
- the durable artifact should be the specification, not one implementation.

### Slide 2 — Tests are useful, but incomplete

Do not say “tests are not evidence.” They are evidence.

Instead say:

- tests demonstrate behaviour on selected cases;
- contracts describe behaviour over a class of cases;
- proofs establish that the abstract model satisfies the contract;
- runtime conformance checking connects the implementation to the model.

This framing respects existing Python practice rather than dismissing it.

### Slide 3 — One specification, several uses

Show:

```text
Contract
  ├── runtime checks
  ├── scenario tests
  ├── generated counterexamples
  ├── AI implementation guidance
  ├── documentation
  └── machine-checked proof
```

This slide should state the value proposition directly.

---

## Section 2: Introduce contracts using ordinary Python

### Slide 4 — A contract is just a set of Python predicates

Do not begin with a mathematical record.

Show a minimal example:

```python
reserve_contract = Contract(
    requires=[
        lambda s, a: a.quantity > 0,
    ],
    ensures=[
        lambda old, a, result, new:
            new.products[a.sku].reserved
            == old.products[a.sku].reserved + a.quantity,
    ],
)
```

Explain only:

- `requires`: valid inputs and starting state;
- `ensures`: what must be true afterwards;
- `reads`: what may influence the result;
- `writes`: what may change;
- `exceptions`: expected failure cases.

The terms “pure” and “terminating” can be introduced afterwards as implementation constraints:

> Specsaver accepts a restricted side-effect-free fragment of Python so that these predicates can be evaluated, translated, and proved.

### Slide 5 — The implementation

Use the existing SQLAlchemy reserve function early. It is familiar and concrete.

### Slide 6 — The specification

Use the existing reserve contract, but simplify it visually.

Do not annotate every clause with multiple technical labels at once. Use a simple visual mapping:

```text
quantity > 0                      valid input
product exists                    required starting state
reserved increases by quantity   required outcome
only these fields may change      write frame
these fields may be consulted     read frame
```

---

## Section 3: Show one end-to-end execution

The current deck lacks a complete running example. Add one.

### Slide 7 — What happens when a scenario runs

Use the reserve example all the way through:

1. build a temporary SQLite database from the scenario;
2. observe the pre-state;
3. check preconditions;
4. run the real SQLAlchemy code;
5. observe the post-state;
6. check the postcondition;
7. check that nothing outside the write frame changed.

This should be the first explanation of the runner.

### Slide 8 — When implementation and contract disagree

Show two possible outcomes:

```text
Contract says reserved increases by 3
Implementation increases it by 4

Result: concrete counterexample
```

Then explain:

- the implementation may be wrong;
- the contract may be wrong;
- the scenario exposes the disagreement;
- the developer resolves it.

Do not call this a “dialectic” in the introductory deck.

### Slide 9 — From tested example to general statement

Explain the progression:

```text
Scenario: one concrete case
Contract: all admissible cases
Proof: abstract correctness of the contract theory
Conformance test: implementation matches the theory on real executions
```

This is the conceptual heart of the presentation.

---

## Section 4: Explain the shared state model

The current “Symmetric Projection” material is important but too abstractly named.

Rename it:

> One state model for testing and proof

or:

> The same specification state is used twice

### Revised explanation

Before execution, Specsaver reads the concrete system into a specification state.

After execution, it applies the same observation function again.

The contract compares those two states.

The proof backend reasons about the corresponding abstract state model.

Avoid claiming that the commuting square itself “guarantees” implementation correctness. The square is an architectural discipline; correctness additionally depends on the projection, model, instrumentation, and conformance arguments being sound.

This point should be stated carefully.

Suggested wording:

> Using the same declared state model for runtime checking and proof prevents the testing and proof layers from silently drifting apart. The remaining trust obligations are explicit: the projection must faithfully observe the concrete system, and the concrete library model must conform to the real library behaviour being relied upon.

This is more accurate than saying the commuting square alone guarantees agreement.

---

# Slide-by-slide review

## Current slide 1 — Title

The title is fine, but “From behavioural features to machine-checked proofs” is still abstract.

Consider a subtitle such as:

> Durable specifications for AI-assisted Python development

This tells the audience why the topic matters.

---

## Current slide 2 — Vibecoding versus Vericoding

### Problems

- It begins with a combative dichotomy.
- “No evidence of correctness” is overstated because tests are evidence.
- “Conformance regime” is unfamiliar jargon.
- Rocq/Coq appears before the audience knows why a proof assistant is relevant.

### Recommended change

Replace this slide with:

> AI can regenerate code. It cannot infer the intent that was never written down.

Then show:

```text
Without a durable specification:
- tests encode selected examples;
- comments drift;
- refactors preserve syntax but may alter behaviour;
- each new model must rediscover the requirements.

With Specsaver:
- intended behaviour is explicit;
- scenarios and code are checked against it;
- proof obligations can be generated from it;
- implementations remain replaceable.
```

The “vibecoding versus vericoding” contrast can be retained later as a conclusion, once the deck has earned it.

---

## Current slide 3 — Two Development Flows

### Strengths

- Distinguishing retrospective and contract-first adoption is useful.
- It shows that Specsaver does not require a greenfield rewrite.

### Problems

- “Testing (dialectic)” is obscure.
- The flow is text-heavy.
- “DISPROVED” may be misleading if the result is sometimes a failed bounded check or concrete counterexample rather than a theorem-level disproof.

### Recommended change

Rename the flows:

- “Adopt around existing code”
- “Build from the contract”

Use a graphical flow.

Use precise status language:

- `PROVED`
- `COUNTEREXAMPLE FOUND`
- `UNKNOWN`

Reserve `DISPROVED` for cases where logical negation has actually been established.

---

## Current slide 4 — Contract Language

### Problems

This slide introduces too many concepts simultaneously:

- pure fragment;
- termination;
- boolean lambdas;
- preconditions;
- postconditions;
- exception semantics;
- invariants;
- derived state;
- frame conditions;
- ghost state;
- a mathematical tuple.

This is the point where a general Python audience is most likely to disengage.

### Recommended change

Split into at least three slides:

1. “A contract is ordinary Python predicates”
2. “What a contract can describe”
3. “Why Specsaver restricts the predicate language”

Move the mathematical record to an appendix or advanced architecture section.

Do not introduce ghost state until there is a concrete example that requires specification-only information.

---

## Current slide 5 — Contract Anatomy: Implementation

### Assessment

This is one of the strongest slides and should appear much earlier.

### Recommended change

Use syntax highlighting and visually mark:

- the database read;
- the branch;
- the database write;
- the returned value.

Do not require the audience to read the whole function at once.

---

## Current slide 6 — Contract Anatomy: Specification

### Assessment

This is also strong, because it makes the contract concrete.

### Problems

- It contains a likely inconsistency in state paths: `s.observed.products` versus `s.products`.
- The exception writes `failure_log`, but the implementation shown does not visibly write such a log.
- The meaning of `state.failure_log` therefore appears under-explained.
- The frame may be too broad or semantically unclear if `failure_log` changes only on exceptional exits.

### Recommended change

Correct or explain these discrepancies.

Use separate success and exceptional write frames where possible.

For example:

```text
success writes:
    products[sku].reserved

InsufficientStockError writes:
    failure_log
```

This will demonstrate that frames are path-sensitive rather than merely global declarations.

---

## Current slides 7 and 8 — Symmetric Projection / Symmetry as Bridge

### Strengths

These slides contain a central architectural idea.

### Problems

- “Symmetric Projection” is not self-explanatory.
- “Commuting diagram” is unnecessary jargon for this audience.
- The claim that the square guarantees implementation/model agreement is too strong.
- The text density is high.

### Recommended change

Merge into one visual slide titled:

> The same state model powers testing and proof

Use a simple diagram:

```text
Real database before ──observe──▶ specification state before
        │                                 │
        │ run Python code                 │ check contract
        ▼                                 ▼
Real database after  ──observe──▶ specification state after
```

Then add a second small panel:

```text
The proof backend reasons over the same declared state structure,
without depending on SQLite or SQLAlchemy.
```

Add a note that the projection and library theory are themselves trust boundaries that require validation.

---

## Current slide 9 — Runner

### Assessment

Good content, but it should appear immediately after the implementation and contract example.

### Recommended change

Use the actual inventory example throughout the six stages.

Avoid abstract terms such as “materialize witness” without a concrete instance.

Say:

> Turn the Gherkin row into a temporary database and function arguments.

Then optionally introduce “witness” as the formal term.

---

## Current slide 10 — Domain Declaration

### Problems

- The slide is implementation-centric.
- It does not explain why this declaration matters to the user.
- The code example is too skeletal to be informative.

### Recommended change

Lead with the benefit:

> Declare the domain once; Specsaver derives the runner, CLI integration, conformance tests, and state projection wiring.

Then show the declaration.

A simple input/output diagram would be more effective than the current line of prose.

---

## Current slide 11 — Theory Stack

### Strengths

The layered structure is technically interesting and demonstrates that Specsaver is not merely testing a mock.

### Problems

- Terms such as `StubHandler`, `operational semantics`, and `final interpretation` are unexplained.
- The central motivation—avoiding an unsound mock—is missing.

### Recommended change

Title it:

> Why a tested model is better than a mock

Explain:

- ordinary mocks may behave differently from SQLAlchemy or the real service;
- Specsaver gives the stub an explicit semantics;
- a differential suite checks that the real library and the model agree on supported operations;
- unsupported behaviour is rejected rather than silently approximated.

This is a compelling point for Python programmers and should be expressed in their terms.

---

## Current slide 12 — Lowering Pipeline

### Assessment

This is a good late-stage slide.

### Problems

- “Lowering,” “shape extraction,” “arms,” “obligation set,” and “bisection” are compiler/prover terminology.
- The distinction between a concrete counterexample and logical disproof is blurred.

### Recommended change

Use a two-layer explanation.

Top line for general audience:

```text
Python contract
→ mathematical statements
→ proof checker
→ proved / counterexample / unknown
```

Bottom line, smaller, for technical detail:

```text
introspection → symbolic IR → Rocq generation → kernel checking
```

This allows both audiences to follow the slide.

---

## Current slide 13 — Formal reserve example

### Problems

- It repeats the contract in notation that is less accessible than the Python version.
- The notation is visually difficult to parse.
- It does not yet teach the audience anything new.

### Recommended change

Either remove it or turn it into a side-by-side translation:

```text
Python predicate                    Generated proposition

quantity > 0                       0 < quantity
reserved' = reserved + quantity    ...
```

The point should be that Specsaver translates the contract automatically, not that users must write mathematical notation themselves.

---

## Current slide 15 — Verified State

### Strengths

Concrete evidence is important.

### Problems

- “6/6, 6/6, 4/4” is not immediately legible.
- “All four store-obligation contracts” is unexplained.
- The scale is small, so the slide should avoid implying industrial validation.

### Recommended change

Use plain language:

> Current prototype status
>
> - 2 example domains
> - 4 store-level contracts
> - 23 generated proof obligations
> - 23 checked successfully by the Rocq kernel

Then add:

> This demonstrates the end-to-end pipeline; it is not yet a large-scale empirical evaluation.

That caveat increases credibility.

---

## Current slide 16 — The Vericoding Promise

### Assessment

The ending is memorable, but “code and hope” may sound dismissive of normal engineering practice.

### Recommended change

A stronger and more defensible conclusion is:

> Generated code is temporary. The specification and its evidence should survive.

Then show:

```text
Implementation can be replaced
Specification remains
Tests remain
Proof evidence remains
```

The existing “vibecoding versus vericoding” phrase can appear here, where the distinction has been explained.

---

# Terminology changes

Use accessible language first and introduce the formal term second.

| Current term | Recommended introductory wording |
|---|---|
| admissibility | valid inputs and starting states |
| postcondition | what must be true afterwards |
| semantic frame | what the operation may read or modify |
| ghost state | specification-only state |
| lowering | translation into the proof model |
| proof obligation | statement that must be proved |
| commuting diagram | the same observation path before and after |
| conformance regime | repeatable checks that implementations satisfy the specification |
| witness | concrete test setup or example state |
| operational semantics | explicit model of how supported operations behave |
| pure terminating fragment | restricted side-effect-free Python used for specifications |

Do not eliminate the formal vocabulary entirely. Introduce it after the intuitive explanation so that the audience learns the correct terms without being blocked by them.

---

# Important technical clarifications

## 1. Testing and proof are not the same claim

The deck should state explicitly:

- scenario tests check concrete executions;
- runtime contract checks compare observed pre- and post-states;
- model proofs establish properties of the abstract state transition theory;
- differential conformance testing provides evidence that the model agrees with the supported concrete library behaviour;
- full end-to-end implementation correctness requires the relevant projection, instrumentation, and model-conformance assumptions.

Avoid language suggesting that proving the abstract contract alone proves arbitrary SQLAlchemy code correct.

## 2. Frames require a clear semantic explanation

For a Python audience, explain frames as:

> The contract does not only say what changes. It also says what must not change.

For the reserve example:

- the selected product’s `reserved` field may change;
- other products must remain unchanged;
- `on_hand` must remain unchanged;
- unrelated tables and logs must remain unchanged unless explicitly listed.

This is a major differentiator and deserves a concrete before/after example.

## 3. Ghost state needs a concrete motivation

Do not introduce ghost state as a bare formal concept.

Introduce it only when needed, for example:

> Some useful facts are not stored directly in the database. Specsaver may track specification-only information such as an initial total balance, an abstract event history, or a logical count. This information guides checking and proof but does not alter production behaviour.

## 4. The role of the AI should be made precise

The deck currently says an LLM closes obligations. Clarify that:

- the LLM may propose proof scripts or implementation code;
- the proof assistant kernel validates proofs;
- untrusted generated output is not accepted merely because the model produced it.

This is one of the strongest aspects of vericoding and should be emphasized.

---

# Suggested replacement deck outline

1. **AI can regenerate code, but not unwritten intent**
2. **Where Python projects currently keep behaviour** — tests, comments, tickets, memory
3. **One executable specification, several uses**
4. **Running example: inventory reservation implementation**
5. **The same behaviour written as a contract**
6. **What `requires`, `ensures`, `reads`, `writes`, and exceptions mean**
7. **Run one real scenario against SQLite and SQLAlchemy**
8. **A frame catches unintended changes**
9. **When contract and implementation disagree**
10. **The same declared state model supports checking and proof**
11. **Why the SQLAlchemy model is differentially tested rather than merely mocked**
12. **From Python predicate to machine-checked theorem**
13. **Two adoption paths: existing code or contract-first**
14. **What has been implemented and proved**
15. **What remains to be validated at larger scale**
16. **Generated code is replaceable; specification and evidence survive**

---

# Suggested tone

The deck should be technically confident without dismissing existing Python practices.

Avoid implying:

- tests are useless;
- ordinary programmers are careless;
- formal verification automatically proves the concrete implementation;
- an LLM producing a proof script makes the proof trusted;
- a small prototype already establishes industrial scalability.

Instead present Specsaver as a disciplined extension of familiar practices:

```text
examples → scenarios
assertions → contracts
fixtures → materialized state
mocks → explicit tested theories
property tests → universal specifications
CI checks → proof checking
```

This framing lowers resistance and makes the novelty easier to understand.

---

# Concrete design guidance

- Use one running example for at least half the deck.
- Reduce text per slide by approximately 30–40%.
- Prefer diagrams and before/after state illustrations to prose.
- Show Python before mathematical notation.
- Do not put more than one new formal concept on a slide.
- Use syntax highlighting consistently.
- Visually distinguish:
  - production code;
  - specification code;
  - observed runtime state;
  - abstract proof state;
  - trusted kernel output.
- Keep Rocq and compiler details in the second half of the deck.
- Put the full contract record and advanced theory stack in an appendix if necessary.

---

# Acceptance criteria for the revision

A Python programmer with no formal methods background should be able to answer the following after viewing the deck:

1. What problem does Specsaver solve?
2. What is a contract in Specsaver?
3. How is it different from an ordinary unit test?
4. What do `reads` and `writes` add?
5. How does Specsaver run a real SQLAlchemy example?
6. What does the state projection do?
7. What exactly is proved in Rocq?
8. What remains a conformance or trust assumption?
9. Why is AI-generated code safer in this workflow?
10. Why would a Python team adopt this incrementally?

If the revised deck does not make these answers clear without supplementary explanation, it remains too internally focused.

---

# Final recommendation

Do not simplify the underlying architecture. Simplify the order in which it is revealed.

The correct progression is:

```text
familiar problem
→ concrete Python example
→ readable contract
→ runtime checking
→ frame checking
→ shared state model
→ abstract proof
→ architecture
```

The current deck largely proceeds in the opposite direction. Reordering it around the Python programmer’s conceptual path will make the technical contribution appear stronger, not weaker.
