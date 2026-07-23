---
theme: default
colorSchema: dark
title: Vericoding — Verification-Driven Development
info: |
  The specsaver toolchain for specification-driven verification:
  from Gherkin features through mathematical contracts to
  machine-checked proof obligations.
class: text-center
drawings:
  persist: false
transition: slide-left
mdc: false
head: '<style>h1{color:#fbbf24 !important}h2{color:#94a3b8 !important;margin-bottom:0.4em}</style>'
exportOptions:
  timeout: 30000
---

# Vericoding

## Verification-Driven Development

From behavioural features to machine-checked proofs

<div class="pt-12">
  <span class="text-gray-400">Gavin Mendel-Gleason · Scidonia · July 2026</span>
</div>

---
layout: two-cols
---

# Vibecoding

The status quo of LLM-driven development.

<br>

<div class="border-l-4 border-red-400 pl-4">

**You prompt.  The model emits.  It runs.**

What you leave behind:

- **No specification** of intended behaviour
- **No evidence** of correctness
- **No conformance regime** for the next generation

The only durable artifact is the code itself.
</div>

::right::

# Vericoding

The methodology specsaver operationalises.

<br>

<div class="border-l-4 border-green-400 pl-4">

**You write a specification.  The spec survives.**

What you leave behind:

- **Features** — Gherkin scenarios domain experts can review
- **Contracts** — mathematical pre/post-conditions
- **Proof obligations** — machine-checked in Rocq/Coq

Generated code is a replaceable implementation detail.
</div>

---

# Two Development Flows

<div class="grid grid-cols-2 gap-6 mt-4">

<div>

## Retrospective

<div class="border-l-4 border-yellow-400 pl-3 text-sm">

- **Feature** — Gherkin scenario tables
- **Implementation** — write the production code
- **Testing (sanity)** — make sure it basically works
- **Contract** — capture observed behaviour as mathematical spec
- **Testing (dialectic)** — re-run under contract checking; either contract or implementation is wrong — the dialectic
- **Formal Proof** — lower to Coq, LLM closes obligations; DISPROVED → back to dialectic

</div>

</div>
<div>

## Contract-First

<div class="border-l-4 border-cyan-400 pl-3 text-sm">

- **Feature** — Gherkin scenario tables
- **Contract** — write spec as acceptance criteria
- **Implementation** — build code against the specification
- **Testing** — validate that implementation satisfies contract
- **Formal Proof** — machine-checked against kernel

</div>

</div>
</div>

<div class="mt-6 text-center text-xs text-green-400 font-bold">
Both converge: the contract is the lasting artifact.<br>
DISPROVED yields witnesses → back to the dialectic.
</div>

---

# Contract Language

<div class="grid grid-cols-2 gap-6 mt-4">

<div>

## The pure terminating fragment of Python

<br>

Every clause is a boolean-valued lambda:

- `requires(state, args)` — admissibility
- `ensures(state, args, result, new_state)` — success post
- `when(state, args)` — exception conditions
- `invariant(state)` — global legality

**Static purity check** rejects side effects,
loops, and non-boolean returns before execution.

</div>
<div>

## Anatomised as mathematical record

<br>

$$
\begin{aligned}
C =\; &\langle \Sigma,\; \mathit{args},\; \mathsf{pre},\; \mathsf{post},\\
      &\quad\; \mathcal{X},\; \mathcal{I},\; \mathcal{D},\; \mathcal{W},\; \mathcal{R},\; \mathcal{G} \rangle
\end{aligned}
$$

<div class="text-sm mt-4">

$\mathcal{X}$  —  exceptional exits (when + ensures + frame)

$\mathcal{I}$  —  invariants on every state

$\mathcal{D}$  —  derived-state definitions

$\mathcal{W}$ / $\mathcal{R}$  —  semantic frame

$\mathcal{G}$  —  ghost state

</div>

</div>
</div>

---

# Contract Anatomy: Implementation

A simple inventory reserve function against SQLAlchemy:

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
The function knows nothing about contracts or specsaver.
It's ordinary SQLAlchemy code with transactions and domain exceptions.
</div>

---

# Contract Anatomy: Specification

The same operation, specified once:

```python
reserve_contract = Contract(
    requires=[
        lambda s, a: a.quantity > 0,
        lambda s, a: a.sku in s.observed.products,
    ],
    ensures=[
        lambda s, a, r, s2: (
            s2.products[a.sku].reserved == s.products[a.sku].reserved + a.quantity),
    ],
    exceptions=[
        ExcExit(raises=InsufficientStockError,
                when=[lambda s, a:
                    s.products[a.sku].on_hand - s.products[a.sku].reserved < a.quantity],
                writes={"state.failure_log"}),
    ],
    writes={"state.products[sku].reserved", "state.failure_log"},
    reads={"state.products[sku].on_hand", "state.products[sku].reserved"},
)
```

<div class="grid grid-cols-4 gap-2 mt-4 text-xs">
<div class="border-l-2 border-blue-400 pl-2"> <b>requires</b><br>admissibility </div>
<div class="border-l-2 border-green-400 pl-2"> <b>ensures</b><br>what changes </div>
<div class="border-l-2 border-red-400 pl-2"> <b>exceptions</b><br>when + outcome </div>
<div class="border-l-2 border-yellow-400 pl-2"> <b>writes/reads</b><br>semantic frame </div>
</div>

---

# Symmetric Projection

<div class="grid grid-cols-2 gap-6 mt-4 text-sm">

<div>

**The commuting diagram.**  One projection `snap`, applied before
and after execution.  Contracts compare the pair.

<div class="my-4">
<div class="inline-block border border-blue-400 rounded px-3 py-1 bg-blue-900/30">Context</div>
<span class="mx-1 text-gray-400">&#8594;</span>
<span class="text-[10px] text-blue-300 mx-0.5">snap</span>
<span class="mx-1 text-gray-400">&#8594;</span>
<div class="inline-block border border-green-400 rounded px-3 py-1 bg-green-900/30">SpecState (pre)</div>
<br>
<div class="text-center w-[80px] inline-block ml-[75px] text-gray-400">&#8595; <span class="text-[10px] text-orange-300">exec</span></div>
<br>
<div class="inline-block border border-blue-400 rounded px-3 py-1 bg-blue-900/30">Context'</div>
<span class="mx-1 text-gray-400">&#8594;</span>
<span class="text-[10px] text-blue-300 mx-0.5">snap</span>
<span class="mx-1 text-gray-400">&#8594;</span>
<div class="inline-block border border-green-400 rounded px-3 py-1 bg-green-900/30">SpecState (post)</div>
</div>

</div>

<div>

**What snap projects.**  `snap : Context → SpecState` reads the concrete world — SQLAlchemy queries → row dicts, event log → typed tuples, pure aggregation → derived fields — and returns a frozen, comparable, purely functional value.  This lifts raw mutable state into the semantic domain where contracts are stated.

**Why symmetry matters.**  The diagram commutes: `snap(exec(ctx)) = post`, and the same `snap` produced `pre`.  Without this guarantee, testing (Python bools) and proving (Coq Props) would reason about different interpretations of state.  Symmetry guarantees they see the same thing.

**What it gives us.**  Contracts written once as pure predicates serve double duty: tested on real rows at runtime, lowering to proof obligations over the same declared schema.  The specification is the source of truth at both levels.

</div>

</div>

---

# Symmetry as Bridge

<div class="mt-4 text-sm">

**Why do testing and proving agree?**  Because the state they see is
produced by the same function.

</div>

<div class="grid grid-cols-3 gap-3 mt-4 text-xs">

<div class="border border-green-800 rounded p-3">
<div class="text-green-300 font-bold mb-2">Declared schema</div>
The contract's `state_schema` names every observed field, its type,
and its provenance.  The runtime snapshot and the Coq state model are
both derived from this single declaration.
</div>

<div class="border border-amber-800 rounded p-3">
<div class="text-amber-300 font-bold mb-2">Semantic frame</div>
`writes` and `reads` are declarative paths over the schema.
The runtime checker and the frame-soundness proof enforce the
same footprint.
</div>

<div class="border border-purple-800 rounded p-3">
<div class="text-purple-300 font-bold mb-2">Same snapshot</div>
One function, called twice.  No divergent "read" and "check" path.
The frame, derived-consistency, and invariant checkers all operate
over this shared interpretation.
</div>

</div>

<div class="mt-6 text-center text-xs text-gray-400">
The specification is the bridge.  Write it once; test it on data today;
prove it against the kernel tomorrow.  The lift is automatic.
</div>

---

# Symmetric Projection — Runner

<div class="grid grid-cols-2 gap-6 mt-6">

<div class="space-y-4">
<div>
<div class="text-orange-300 font-bold">1. materialize</div>
<div class="text-sm text-gray-400">witness → temp SQLite DB + engine + EventLog</div>
</div>
<div>
<div class="text-orange-300 font-bold">2. pre-check</div>
<div class="text-sm text-gray-400">invariants on pre-state; admissibility (requires)</div>
</div>
<div>
<div class="text-orange-300 font-bold">3. execute</div>
<div class="text-sm text-gray-400">service runs against real SQLite via SQLAlchemy; wrapper emits typed events into the log</div>
</div>
</div>

<div class="space-y-4">
<div>
<div class="text-orange-300 font-bold">4. frame check</div>
<div class="text-sm text-gray-400">everything outside writes unchanged</div>
</div>
<div>
<div class="text-orange-300 font-bold">5. derived check</div>
<div class="text-sm text-gray-400">derived fields ≡ recomputed from observed</div>
</div>
<div>
<div class="text-orange-300 font-bold">6. post-check</div>
<div class="text-sm text-gray-400">ensures (or exit ensures) for the outcome; invariants on post-state</div>
</div>
</div>

</div>

---
---

# Domain Declaration

One object → runners, CLI, conformance suite.

```python
inventory = SqlDomain(
    name         = "inventory",
    package      = "examples.inventory",
    materializer = SqlMaterializer(ddl, TableSpec[]),
    projection   = SqlProjection(types, hooks),
    operations   = [
        SqlOperation(contract, wrapper,
                     witness_builder, feature_file),
        ...
    ]
)
```

<div class="grid grid-cols-3 gap-4 mt-4 text-sm">
<div class="border border-cyan-800 rounded p-2 text-center">scenario runners</div>
<div class="border border-cyan-800 rounded p-2 text-center">CLI dispatch</div>
<div class="border border-cyan-800 rounded p-2 text-center">conformance tests</div>
</div>

<div class="mt-4 text-sm text-gray-400">
Adding a domain: types + service + contracts + features + witness builders + one declaration.
Everything else (materializer, projection, runner wiring, test dispatch) is derived.
</div>

---
---

# Theory Stack

Services run **unmodified** on differentially-tested stubs.

<div class="space-y-1 mt-6 text-sm">
<div class="bg-blue-900/30 rounded p-2">
<span class="text-blue-300 font-bold">Service</span>
<span class="text-gray-400 ml-2">ordinary SQLAlchemy / logging / OTel API code</span>
</div>

<div class="bg-orange-900/30 rounded p-2">
<span class="text-orange-300 font-bold">Shim</span>
<span class="text-gray-400 ml-2">make_engine, make_log_capture, make_otel_capture</span>
</div>

<div class="bg-green-900/30 rounded p-2">
<span class="text-green-300 font-bold">StubHandler</span>
<span class="text-gray-400 ml-2">operational semantics over the state model</span>
</div>

<div class="bg-green-900/20 rounded p-2">
<span class="text-green-400 font-bold">State model</span>
<span class="text-gray-400 ml-2">TableStore / LogStore / OtelStore</span>
</div>

<div class="bg-gray-800 rounded p-2">
<span class="text-gray-500 font-bold">Trace</span>
<span class="text-gray-400 ml-2">final interpretation (events)</span>
</div>
</div>

<div class="mt-6 border border-purple-800 rounded p-3 text-sm">
<span class="text-purple-300 font-bold">Theory conformance:</span>
Stub and real library agree observationally on a differential suite;
translator rejects out-of-fragment input loudly;
state model and trace are pure data.
</div>

---
---

# Lowering Pipeline

<div class="grid grid-cols-4 gap-3 mt-8">
<div class="bg-blue-900/30 rounded p-3 text-center">
<span class="text-blue-300 block text-lg font-bold">Contract</span>
<span class="text-xs text-gray-400">Python lambdas</span>
</div>
<div class="text-2xl self-center text-center">→</div>
<div class="bg-orange-900/30 rounded p-3 text-center">
<span class="text-orange-300 block text-lg font-bold">introspect</span>
<span class="text-xs text-gray-400">shape extraction<br>deltas, scalars, arms</span>
</div>
<div class="text-2xl self-center text-center">→</div>
<div class="bg-orange-900/30 rounded p-3 text-center">
<span class="text-orange-300 block text-lg font-bold">emit</span>
<span class="text-xs text-gray-400">gen_pre / gen_post<br>+ obligation set</span>
</div>
<div class="text-2xl self-center text-center">→</div>
<div class="bg-green-900/30 rounded p-3 text-center">
<span class="text-green-300 block text-lg font-bold">score</span>
<span class="text-xs text-gray-400">coqc compile<br>per-obligation bisection</span>
</div>
</div>

<div class="grid grid-cols-3 gap-4 mt-8">
<div class="bg-green-900/40 rounded p-4 text-center">
<span class="text-green-300 font-bold text-xl block">PROVED</span>
<span class="text-xs text-gray-400">machine-checked against kernel</span>
</div>
<div class="bg-yellow-900/30 rounded p-4 text-center">
<span class="text-yellow-300 font-bold text-xl block">UNKNOWN</span>
<span class="text-xs text-gray-400">queued for LLM proof oracle</span>
</div>
<div class="bg-red-900/30 rounded p-4 text-center">
<span class="text-red-300 font-bold text-xl block">DISPROVED</span>
<span class="text-xs text-gray-400">runtime counterexample found</span>
</div>
</div>

---
---

# Example: Inventory Reserve

<div class="text-sm">

**Pre-condition:**
$$
\mathsf{pre}(s, a) \;=\; a.\mathit{quantity} > 0 \;\wedge\; a.\mathit{sku} \in s.\mathit{products}
$$

**Post-condition:**
$$
\mathsf{post}(s, a, r, s') \;=\;
s'.reserved = s.reserved + a.quantity
\;\land\;
\mathsf{extends\_by\_one}(s.res\_log, s'.res\_log, \ldots)
$$

**Exception exit:**
$$
\mathcal{X} = \{\,
\langle \mathsf{InsufficientStock},\;
s.available < a.quantity,\;
\{failure\_log\}
\rangle \,\}
$$

</div>

---
---

---

# Verified State

<table class="text-sm w-full mt-4">
<tr><th>Domain</th><th>Tables</th><th>Ops</th><th>Rows</th><th>Obligations</th></tr>
<tr><td>inventory</td><td>1</td><td>3</td><td>22</td><td>6/6, 6/6, 4/4</td></tr>
<tr><td>bank_transfer</td><td>2</td><td>1</td><td>11</td><td>7/7</td></tr>
<tr><td><b>Total</b></td><td></td><td><b>6</b></td><td><b>42</b></td><td><b>23/23</b></td></tr>
</table>

<div class="mt-6 text-sm text-gray-400">
All four store-obligation contracts fully proved in Rocq.
</div>

---

# The Vericoding Promise

<div class="text-lg text-center mt-8 space-y-6">

<div class="border border-red-800 rounded p-4 max-w-lg mx-auto">
<span class="text-red-300 font-bold">Vibecoding leaves</span><br>
<span class="text-gray-400">code and hope</span>
</div>

<div class="text-3xl text-gray-500">⬇</div>

<div class="border border-green-800 rounded p-4 max-w-lg mx-auto">
<span class="text-green-300 font-bold">Vericoding leaves</span><br>
<span class="text-gray-400">a specification and evidence</span>
</div>

</div>
