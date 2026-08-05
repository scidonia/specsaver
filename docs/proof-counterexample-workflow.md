# Proof and Counter-Example Workflow

Working document — the three-valued outcome model for obligation
verification with rocq-piler.  Covers: where falsity comes from, what
counts as a proof, what counts as a disproof, and the constraints both
must satisfy to be accepted.

## 1. The alignment problem

A contract is a claim about intended behaviour.  An implementation is a
claim about actual behaviour.  Either can be wrong:

- **Specification bug** — the contract does not reflect the intention
  (wrong arithmetic, missing availability check, wrong frame).
- **Implementation error** — the code does not match the contract
  (the code does something the contract forbids, or fails to do what
  the contract requires).

Obligations are derived from contracts.  **Some obligations will
therefore be false.**  A verification tool that only answers "proved"
is incomplete: a false obligation is not merely unprovable, it is
*decidably untrue*, and that fact is itself valuable evidence.  The
verifier must be able to say so — with a witness.

## 2. Three-valued outcomes

Every obligation, in every obligation set, resolves to exactly one of:

| Outcome | Meaning | Evidence |
|---|---|---|
| **PROVED** | The obligation is true, certified | Kernel-checked closure under the constraints of §4 |
| **DISPROVED** | The obligation is false, certified | A concrete counter-example, extractable (§5) |
| **UNKNOWN** | Neither certified | Explicit give-up with a reason (budget, search space) |

Critical distinction: **DISPROVED requires positive evidence.**
Without a witness, a false obligation is UNKNOWN, not DISPROVED.
"Probably false" is not a verdict.

**Any modification of the obligation's statement makes the outcome
UNPROVED, regardless of what else happened.**  The statement is the
contract of truth; a prover that rewrites it has answered a different
question.

## 3. The obligation package

The emitter produces, per contract, a self-contained package:

```
coq/gen/<contract>/
  _CoqProject
  <name>_defs.v            — gen_pre/gen_post/gen_table, invariants, defs hash
  <name>_L0.v              — admissibility + exit coverage
  <name>_L1.v              — spec consistency (totality)
  <name>_L2.v              — helper lemmas
  <name>_L3.v              — invariant preservation + frame soundness
  <name>_Lneg.v            — evidential negations + candidate witnesses
  schedule.json            — dependency DAG for parallel proving
  _skill.md                — proof patterns (unified SnakeletExn skill)
  statements.json          — hash of every obligation statement
```

`statements.json` records, per obligation, `(name, statement_hash)`.
The hash covers the lemma name and its full type, nothing else.  This
is what makes statement-immutability mechanically checkable.

## 4. PROVED — validity conditions

A closure counts as PROVED only if all of the following hold:

1. **Statement unchanged.**  The obligation's `(name, statement)` hash
   after proving equals the hash in `statements.json`.
2. **No new axioms.**  `Print Assumptions <lemma>` reports closure
   under the global context plus only what the obligation file itself
   provides (the `FunCtx`/heapGS instances and any `Hypothesis`
   entries already present, e.g. library specs like `Hen_lookup`).
   Any `Axiom`, `Parameter`, or new `Hypothesis` introduced by the
   prover invalidates the proof.
3. **No holes.**  The proof term contains no `admit`, the file gains
   no `Admitted`, and no goal is shelved.  `Print Assumptions` catches
   all of these; a text-level check on the proof body is the fast path.
4. **Kernel acceptance.**  `coqc` compiles the file.  coq-lsp
   accepting is not sufficient — the kernel is the judge.

Permitted prover activity: writing proof bodies between `Proof.` and
`Qed.`, and adding *new* helper lemmas (with their own proofs) above
the obligation.  Everything else — definitions, obligation statements,
the context — is read-only.

## 5. DISPROVED — validity conditions

A disproof counts only if the counter-example is *evidential* and
*extractable*:

1. **Witness as data.**  A `CounterWitness` record holding the
   concrete initial state, arguments, and the computed offending
   result.  Pure data — no Prop fields.

   ```coq
   Record CounterWitness := {
     cw_store   : list (sn_val * sn_val);
     cw_sku     : string;
     cw_args    : list sn_val;
     cw_bad_row : sn_val;
   }.
   ```

2. **Satellite lemmas, all computational.**  Each is closed by
   `reflexivity`, `vm_compute`, `inversion/injection`, or `lia` —
   never by search:

   ```coq
   Lemma cex_pre_holds : gen_pre buggy_sigma cex.(cw_args).
   Lemma cex_update_computes :
     dict_insert_str cex.(cw_sku) cex.(cw_bad_row) cex.(cw_store)
     = [(LitString cex.(cw_sku), cex.(cw_bad_row))].
   Lemma cex_violates_inv : ~ row_inv cex.(cw_bad_row).
   ```

3. **Bundling theorem references the original definitions.**  The
   negation must be stated over `gen_pre`/`gen_post`/`row_inv` of the
   obligation file — not restated or simplified copies:

   ```coq
   Theorem reserve_preservation_false :
     exists store_d sku qty,
       dict_lookup_str sku store_d = Some (row_of 10 8 5) /\
       ~ store_inv (dict_insert_str sku (row_of 10 13 5) store_d).
   ```

4. **Extractable.**  `Eval compute in cex` yields the concrete
   witness (state, args, bad result) in a form a human can read and
   the scenario materializer can run against the real library for a
   runtime double-check.

5. **Same closure constraints as PROVED.**  Statement unchanged, no
   new axioms, no holes, kernel acceptance.

## 6. UNKNOWN — the honest third value

UNKNOWN is recorded with a machine-readable reason:

- `timeout` — prover budget exhausted
- `no_witness` — obligation looks false but no candidate witness was
  available or certifiable (§7)
- `missing_lemma` — a needed library spec is absent from the FunCtx
- `stuck` — proof state the prover could not advance

UNKNOWN is not failure; it is a routing signal.  UNKNOWN obligations
go to the human or to a stronger oracle.  They never silently block
the scoreboard — every other obligation still reports its own value.

## 7. The witness lifecycle

Witnesses have two sources, and the package supports both:

**Hand-picked (authored).**  When a false contract is written on
purpose (regression test, spec review), the witness is authored with
it and emitted into `<name>_Lneg.v` directly.

**Scenario-discovered (the dialectic loop).**  The scenario runner
executes the contract's feature tables against the real library.  A
failing row is a *candidate* witness: it has a concrete initial state
and concrete arguments.  The runner reports candidates as JSON:

```json
{ "obligation": "invariant_preservation",
  "store": {"SKU1": {"on_hand": 10, "reserved": 8, "reorder_point": 5}},
  "args": ["SKU1", "ORDER1", 5],
  "computed": {"on_hand": 10, "reserved": 13, "reorder_point": 5} }
```

The emitter materializes each candidate into `<name>_Lneg.v` as a
`CounterWitness` definition plus the satellite lemmas.  The prover
then *certifies* the candidate: if all satellites close and the
bundling theorem compiles, the obligation is DISPROVED with that
witness.  If the candidate does not certify (the "failure" was a
runner artifact, not a real violation), the obligation returns to
UNKNOWN or PROVED as the evidence dictates.

If no candidate exists and the obligation will not close, the prover
may attempt witness search — but bounded.  Unbounded search is the
fast path to UNKNOWN, and that is correct: UNKNOWN with a reason is
more useful than an open-ended hunt.

## 8. Prover protocol (rocq-piler side)

Per obligation, at any juncture, the prover chooses:

1. **Attempt PROVED** under the §4 constraints.  Edits restricted to
   proof bodies and new helper lemmas.  Statement regions are
   read-only — enforced by the hash check, not by trust.
2. **Attempt DISPROVED** under the §5 constraints, using the
   candidate witnesses in `<name>_Lneg.v`.  All three satellites plus
   the bundling theorem must close.
3. **Declare UNKNOWN** with a §6 reason.

The prover may switch between (1) and (2) freely — a PROVED attempt
that stalls is evidence for trying DISPROVED, and vice versa.  What
it may never do is modify the statement, add axioms, or leave holes
and call the result a proof.

Parallelism: `schedule.json` marks layers as independent; L0–L3 and
Lneg prove concurrently.  The scoreboard is per-obligation, not
per-contract — a contract can be mostly PROVED with one obligation
DISPROVED and one UNKNOWN, and that is a complete, honest answer.

## 9. Outcome → action

| Where DISPROVED lands | Diagnosis | Action |
|---|---|---|
| Contract obligation (L0–L3) | Specification bug | Fix the contract |
| Lowering refinement (implementation WP) | Implementation error | Fix the code — or the contract, if the code is the intention |
| Both | Genuine misalignment | The witness tells you which side the arithmetic disagrees with |
| UNKNOWN anywhere | Insufficient evidence | Human review or stronger oracle |

The counter-example is the payload: it names the state, the
arguments, and the exact value where the invariant breaks.  That is
what makes the loop close — the human does not debug, they read the
witness and decide which side is wrong.

## 10. What we need to build

- **Emitter**: `statements.json` hashing; `<name>_Lneg.v` generation
  from authored witnesses and from runner-reported candidates
  (JSON → `CounterWitness` + satellites + bundling theorem).
- **Runner**: report failing scenario rows in the candidate-witness
  JSON form above.
- **rocq-piler**: the prove/disprove/unknown protocol of §8, with
  statement-hash immutability enforcement and `Print Assumptions`
  closure checks as first-class verdict gates.
- **Scoreboard**: three-valued per-obligation status with reasons,
  consumed by the dialectic loop.
