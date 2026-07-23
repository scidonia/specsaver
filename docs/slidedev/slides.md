---
theme: default
colorSchema: dark
title: Specsaver — Durable Specifications for Python
head: '<style>h1{color:#fbbf24 !important}h2{color:#94a3b8 !important;margin-bottom:0.4em}</style>'
---

# Specsaver

## Durable specifications for AI-assisted Python development

<div class="pt-12">
  <span class="text-gray-400">Gavin Mendel-Gleason · Scidonia</span>
</div>

---

# AI Can Regenerate Code

## It Cannot Infer Intent That Was Never Written

```python
# What does this function guarantee?
def reserve(engine, sku, order_id, quantity):
    with engine.begin() as conn:
        row = conn.execute(...).fetchone()
        if available < quantity: raise InsufficientStockError
        conn.execute("UPDATE products SET reserved = reserved + :qty ...")
    return ReservationReceipt(sku=sku, quantity=quantity)
```

<div class="mt-6 text-sm text-gray-400">
An LLM can rewrite this function in a second.  But what was it
<b>supposed</b> to do?  Without a durable specification, the
intent is lost the moment the code changes.
</div>

---

# Where Behaviour Lives Today

<div class="grid grid-cols-2 gap-6 mt-4 text-sm">

<div>

**Scattered across:**

- Unit tests encode selected examples
- Comments drift from the code
- Tickets describe the original request
- Memory of the original developer

**When the code changes:**
- Tests may miss the changed behaviour
- Comments become obsolete overnight
- Tickets are closed and forgotten

</div>

<div>

**What we want:**

- Intent is explicit and machine-checkable
- The same spec drives testing, checking, and proof
- When code changes, the spec doesn't
- AI-assisted rewrites are validated against the spec

<div class="mt-4 border-l-4 border-amber-400 pl-3 text-xs text-amber-300">
Every Python project already has a specification — it's just scattered.
Specsaver puts it into a single executable artifact.
</div>

</div>

</div>

---

# One Specification, Several Uses

<div class="grid grid-cols-3 gap-4 mt-8">
<div class="border border-green-800 rounded p-4 text-center">
<div class="text-green-300 font-bold">Runtime Checking</div>
<div class="text-xs text-gray-400 mt-2">pre/post conditions checked on every execution</div>
</div>
<div class="border border-blue-800 rounded p-4 text-center">
<div class="text-blue-300 font-bold">Scenario Testing</div>
<div class="text-xs text-gray-400 mt-2">every Gherkin Examples row exercised against the contract</div>
</div>
<div class="border border-orange-800 rounded p-4 text-center">
<div class="text-orange-300 font-bold">AI Guidance</div>
<div class="text-xs text-gray-400 mt-2">regenerated code validated against the existing spec</div>
</div>
<div class="border border-purple-800 rounded p-4 text-center">
<div class="text-purple-300 font-bold">Documentation</div>
<div class="text-xs text-gray-400 mt-2">the contract IS the behavioural documentation</div>
</div>
<div class="border border-red-800 rounded p-4 text-center">
<div class="text-red-300 font-bold">Counterexamples</div>
<div class="text-xs text-gray-400 mt-2">mismatches between impl and spec surface automatically</div>
</div>
<div class="border border-cyan-800 rounded p-4 text-center">
<div class="text-cyan-300 font-bold">Machine Proof</div>
<div class="text-xs text-gray-400 mt-2">universal properties checked by the Rocq proof kernel</div>
</div>
</div>

---

# Running Example: Inventory Reserve

An ordinary Python function against SQLAlchemy:

```python
def reserve(self, engine, sku, order_id, quantity):
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT on_hand, reserved FROM products"
                 " WHERE sku = :sku"), {"sku": sku}
        ).fetchone()

        if row is None: raise ProductNotFoundError(sku)

        on_hand, reserved = row
        available = on_hand - reserved

        if available < quantity:
            raise InsufficientStockError(sku, quantity, available)

        conn.execute(
            text("UPDATE products SET reserved = reserved + :qty"
                 " WHERE sku = :sku"),
            {"qty": quantity, "sku": sku},
        )

    return ReservationReceipt(sku=sku, quantity=quantity)
```

<div class="text-xs text-gray-400 mt-2">
This function knows nothing about Specsaver.  It's ordinary SQLAlchemy
with transactions and domain exceptions.
</div>

---

# The Same Behaviour as a Contract

```python
reserve_contract = Contract(
    requires=[
        lambda s, a: a.quantity > 0,              # valid input
        lambda s, a: a.sku in s.products,         # product exists
    ],
    ensures=[
        lambda s, a, r, s2: (                     # what must hold after
            s2.products[a.sku].reserved
            == s.products[a.sku].reserved + a.quantity),
    ],
    exceptions=[
        ExcExit(raises=InsufficientStockError,
                when=[lambda s, a:
                    s.products[a.sku].on_hand
                  - s.products[a.sku].reserved < a.quantity]),
    ],
    writes={"state.products[sku].reserved"},
    reads={"state.products[sku].on_hand",
           "state.products[sku].reserved"},
)
```

<div class="text-xs text-gray-400 mt-2">
One spec.  Tested on real data.  Lowered to proof obligations.
</div>

---

# What Each Clause Means

<div class="grid grid-cols-2 gap-4 mt-4 text-sm">

<div class="border-l-4 border-blue-400 pl-3">
<b>requires</b> — valid inputs and starting state<br>
<span class="text-gray-400 text-xs">checked before every call; rejected scenarios fail here</span>
</div>

<div class="border-l-4 border-green-400 pl-3">
<b>ensures</b> — what must be true afterwards<br>
<span class="text-gray-400 text-xs">checked after every successful call against the post-state</span>
</div>

<div class="border-l-4 border-red-400 pl-3">
<b>exceptions</b> — expected failure cases<br>
<span class="text-gray-400 text-xs">"when this condition holds, this error must be raised"</span>
</div>

<div class="border-l-4 border-yellow-400 pl-3">
<b>writes / reads</b> — what may change, what may be consulted<br>
<span class="text-gray-400 text-xs">everything else is checked unchanged — no manual "unchanged" clauses</span>
</div>

</div>

<div class="mt-6 text-xs text-gray-400">
The contract language is a <b>restricted, side-effect-free fragment of Python</b>.
Predicates cannot modify state, call I/O, or raise exceptions — so they are safe
to execute, translate, and prove.
</div>

---

# Run One Scenario

<div class="text-sm">

A Gherkin row: <span class="text-amber-300">sku=S1, on_hand=100, reserved=10, quantity=30</span>

<div class="grid grid-cols-2 gap-4 mt-4 text-xs">

<div class="space-y-2">
<div class="text-orange-300 font-bold">1. Materialize</div>
<div class="text-gray-400">Turn the row into a temp SQLite database and function arguments</div>

<div class="text-orange-300 font-bold">2. Pre-check</div>
<div class="text-gray-400">Take a snapshot of the database state; check <b>requires</b></div>

<div class="text-orange-300 font-bold">3. Execute</div>
<div class="text-gray-400">Run the real <tt>reserve()</tt> function against SQLAlchemy on the temp database</div>
</div>

<div class="space-y-2">
<div class="text-orange-300 font-bold">4. Frame check</div>
<div class="text-gray-400">Verify only <tt>products[S1].reserved</tt> changed — nothing else did</div>

<div class="text-orange-300 font-bold">5. Derived check</div>
<div class="text-gray-400">Recompute totals from the snapshot; confirm they are consistent</div>

<div class="text-orange-300 font-bold">6. Post-check</div>
<div class="text-gray-400">Take a second snapshot; check <b>ensures</b> and invariants</div>
</div>

</div>

</div>

---

# Frames Catch Unintended Changes

<div class="grid grid-cols-2 gap-6 mt-4 text-sm">

<div>

**The contract declares what may change:**

```python
writes = {"state.products[sku].reserved"}
```

**Specsaver checks that:**

- `reserved` for the selected product changed correctly
- `on_hand` for that product is unchanged
- every other product row is untouched
- other tables and logs are unchanged

</div>

<div>

**Why this matters.**

Without frame checking, a refactor can silently mutate
bystander state — a different product, an unrelated table,
a log channel — and no test will catch it unless it was
specifically written for that row.

The frame is <b>derived</b> from the write declaration.
You never write "everything else unchanged."

</div>

</div>

---

# When Contract and Implementation Disagree

<div class="grid grid-cols-2 gap-6 mt-4 text-sm">

<div>

**The contract says:**

```text
reserved increases by 30
```

**The implementation does:**

```text
reserved increases by 40
```

<div class="mt-4 p-3 bg-red-900/20 border border-red-800 rounded text-xs">
<b>Result:</b> a concrete counterexample is surfaced.
</div>

</div>

<div>

**Either the code is wrong, or the contract is wrong.**

<div class="mt-4 space-y-3 text-xs">

<div class="border-l-4 border-amber-400 pl-2">
The scenario exposes the disagreement as a concrete failure — not a vague suspicion, but a specific row with specific values.
</div>

<div class="border-l-4 border-green-400 pl-2">
The developer resolves it: fix the code, or fix the contract.  The contract is a
<b>living artifact</b> — it evolves with the code, but it remains the source of truth.
</div>

</div>

</div>

</div>

---

# The Same State Model for Testing and Proof

<div class="grid grid-cols-2 gap-6 mt-4 text-sm">

<div>

**Before execution,** Specsaver reads the concrete system into a
specification state.

**After execution,** it applies the same observation function again.

**The contract compares those two states.**

<div class="my-4 text-xs text-gray-400">
  Real DB before &nbsp;──observe──→ &nbsp;spec state before<br>
  &nbsp;&nbsp;&nbsp;&nbsp;│ &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;│<br>
  &nbsp;&nbsp;&nbsp;&nbsp;│ run code&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;│ check contract<br>
  &nbsp;&nbsp;&nbsp;&nbsp;↓ &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;↓<br>
  Real DB after &nbsp;&nbsp;──observe──→ &nbsp;spec state after
</div>

</div>

<div>

**Testing and proof share the same declared state structure.**

<div class="space-y-3 text-xs mt-4">

<div class="border-l-2 border-green-400 pl-2">
<b>At runtime:</b> the contract predicates evaluate to Python bool
on real database state — concrete evidence.
</div>

<div class="border-l-2 border-purple-400 pl-2">
<b>At proof time:</b> the same predicates are translated to Rocq
propositions over an abstract model — universal guarantees.
</div>

<div class="border-l-2 border-amber-400 pl-2">
<b>One model, two levels.  Abstract proofs reason purely about
spec-state evolution — no SQLite, no engine.</b>
</div>

</div>

</div>

</div>

---

# Why a Tested Model Beats a Mock

<div class="text-sm mt-4">

**The Problem with Mocks**

Ordinary mocks simulate library behaviour but have no verified semantics.
They may silently accept unsupported operations or return different results
from the real library.

**Specsaver's Approach: Differential Testing**

Each library theory (SQLAlchemy, logging, OpenTelemetry) ships with a
<b>differential fidelity suite</b> — the same program runs against the
real library and against the theory model.  Results must agree on the
supported fragment.

<div class="mt-4 grid grid-cols-3 gap-3 text-xs">
<div class="border border-green-800 rounded p-3">
<div class="text-green-300 font-bold">Covered operations</div>
Stub and real library produce identical results — verified by the suite.
</div>
<div class="border border-red-800 rounded p-3">
<div class="text-red-300 font-bold">Out-of-fragment</div>
Rejected loudly — no silent approximation of unsupported behaviour.
</div>
<div class="border border-blue-800 rounded p-3">
<div class="text-blue-300 font-bold">State model</div>
Operations interpreted over a pure, inspectable state model — not a mock.
</div>
</div>

</div>

---

# From Python Predicate to Machine-Checked Theorem

<div class="text-sm">

```text
Python contract ──→ mathematical propositions ──→ Rocq proof kernel ──→ verdict
```

<div class="grid grid-cols-3 gap-4 mt-6">

<div class="border border-green-900/40 rounded p-4 text-center">
<span class="text-green-300 font-bold text-xl block">PROVED</span>
<span class="text-xs text-gray-400">machine-checked by the kernel</span>
</div>

<div class="border border-yellow-900/30 rounded p-4 text-center">
<span class="text-yellow-300 font-bold text-xl block">UNKNOWN</span>
<span class="text-xs text-gray-400">queued for AI-assisted proof</span>
</div>

<div class="border border-red-900/30 rounded p-4 text-center">
<span class="text-red-300 font-bold text-xl block">COUNTEREXAMPLE</span>
<span class="text-xs text-gray-400">concrete failure found at runtime</span>
</div>

</div>

<div class="mt-6 text-xs text-gray-400">
The AI may propose proof scripts — but only the Rocq kernel validates them.
Untrusted output is never accepted merely because a model produced it.
</div>

</div>

---

# Two Adoption Paths

<div class="grid grid-cols-2 gap-6 mt-4 text-sm">

<div class="border-l-4 border-yellow-400 pl-3">

### Adopt Around Existing Code

- Feature — Gherkin scenario tables
- Implementation — write the production code
- Testing (sanity) — make sure it basically works
- **Contract** — capture observed behaviour as a spec
- Testing (contract) — re-run under contract checking
- Formal proof — lower to Rocq

<div class="text-xs text-gray-400 mt-2">
Start with the code you have.  Write contracts that describe what
it already does.  The contract validates existing behaviour.
</div>

</div>

<div class="border-l-4 border-cyan-400 pl-3">

### Build from the Contract

- Feature — Gherkin scenario tables
- **Contract** — write spec as acceptance criteria
- Implementation — build code against the spec
- Testing — validate the implementation
- Formal proof — machine-checked guarantee

<div class="text-xs text-gray-400 mt-2">
Write the spec first.  Use it as acceptance criteria and
AI-implementation guidance.  Code becomes replaceable.
</div>

</div>

</div>

<div class="mt-6 text-center text-xs text-green-400 font-bold">
Both paths converge on a durable specification that survives code changes.
</div>

---

# What Has Been Implemented and Proved

<div class="grid grid-cols-2 gap-6 mt-4 text-sm">

<div>

**Current prototype status:**

<table class="text-xs w-full mt-2">
<tr><th>Domain</th><th>Ops</th><th>Rows</th><th>Obligations</th></tr>
<tr><td>inventory</td><td>3</td><td>22</td><td>6/6, 6/6, 4/4 proved</td></tr>
<tr><td>bank_transfer</td><td>1</td><td>11</td><td>7/7 proved</td></tr>
<tr><td><b>Total</b></td><td><b>4</b></td><td><b>33</b></td><td><b>23/23 proved</b></td></tr>
</table>

<div class="text-xs text-gray-400 mt-2">
This demonstrates the end-to-end pipeline at prototype scale.
</div>

</div>

<div>

**What's trusted, what's proved:**

<div class="space-y-2 text-xs mt-2">

<div class="border-l-2 border-green-400 pl-2">
<b>Proved:</b> store-obligation consistency, frame soundness,
invariant preservation — checked by the Rocq kernel.
</div>

<div class="border-l-2 border-amber-400 pl-2">
<b>Trusted:</b> the projection observes the concrete system faithfully;
the library theory conforms to the real library behaviour.
</div>

<div class="border-l-2 border-red-400 pl-2">
<b>Ongoing:</b> trace/event obligations, larger-scale evaluation,
counterexample surfacing from the runner into the scoreboard.
</div>

</div>

</div>

</div>

---

# Generated Code Is Replaceable

## The Specification and Its Evidence Survive

<div class="text-lg text-center mt-8 space-y-6">

<div class="border border-red-800 rounded p-4 max-w-lg mx-auto">
<span class="text-red-300 font-bold">Without a durable specification</span><br>
<span class="text-gray-400">code is rewritten and intent is lost</span>
</div>

<div class="text-3xl text-gray-500">⬇</div>

<div class="border border-green-800 rounded p-4 max-w-lg mx-auto">
<span class="text-green-300 font-bold">With Specsaver</span><br>
<span class="text-gray-400">implementation can be replaced; specification, tests, and proof evidence remain</span>
</div>

</div>

<div class="mt-12 text-center text-sm text-gray-400">
specsaver · github.com/scidonia/specsaver
</div>
