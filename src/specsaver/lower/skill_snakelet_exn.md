# SnakeletExn Proof Patterns (Iris / gmap / stdpp)

Unified guidance for Rocq proofs over SnakeletExn: contract obligations
(FunSpecS) and implementation-lowering WP refinements (`wp_exn`).

---

## Part I — Kernel & stdpp pitfalls

### decide opacity
`rewrite lookup_insert` introduces `if decide (k = k) then ...`.
The `decide` typeclass from stdpp is opaque at Qed time —
`destruct (decide (k = k))` produces a kernel-rejected proof term.
Always use `rewrite decide_True; reflexivity` or
`apply lookup_insert_eq` instead.

### gmap singletons — CRITICAL
**NEVER use `set`, `pose`, or `refine` for the sigma witness.**
They make the map opaque to the kernel — coq-lsp will accept the proof
but coqc rejects it. Always provide sigma directly inside `exists`:

```coq
(* CORRECT — works with both coq-lsp and coqc *)
exists {[store_loc := LitDict [...]; trace_loc := LitList []]},
       [LitString "SKU1"; ...].
split.
  - ... apply lookup_insert_eq ...
  - ...

(* WRONG — coq-lsp accepts, coqc rejects *)
set (sigma := {[store_loc := ...]}).  (* opaque to kernel *)
...
unfold sigma. ... reflexivity.         (* coqc can't unify *)
```

The `exists` must receive the map literal directly so the kernel sees a
concrete value, not a named definition. `apply lookup_insert_eq` for
same-key lookup. For multi-key: first key uses `lookup_insert_eq`,
subsequent keys use `rewrite lookup_insert_ne; [exact ... | congruence]`.

### `cbn` without arguments unfolds `wp_exn`
After `iApply wp_let`, bare `cbn` is fine only when the next step is another
`iApply` (unification tolerates the unfolding). If the next step is a
`lazymatch`-based tactic, it will fail — `wp_exn` is now a raw fixpoint.
Prefer `simpl subst` or `cbn [subst]` when in doubt.

---

## Part II — Contract obligations (FunSpecS layers)

### gen_table_total
The shared defs file exports `gen_table_total` — one lemma for all
spec-consistency proofs: if `gen_table f = Some (FunSpecS pre post)`
and `pre sigma vs`, then
`exists r ups, post sigma vs r ups /\ updates_dom_in sigma ups`.
Use `eapply (gen_table_total "fn" pre post vs sigma eq_refl Hpre)`.
Function names match `gen_table` dispatch keys (contract name for success,
`<name>_exc<i>` for exception arms).

### updates_dom_in / Forall
`unfold updates_dom_in. constructor.` when ups = [].
For singleton ups: `unfold updates_dom_in; simpl; split;
[rewrite Hlookup; eauto | constructor]`.

### store_inv
`store_inv [(_, v)]` simplifies to `row_inv v /\ True`.
Use `unfold store_inv; simpl; split; [| exact I]`.

### dict_lookup_str
`simpl` reduces matching-key lookups — `String.eqb k k` reduces to `true`.
Use `simpl; reflexivity`.

### row_inv
Unfold to existential over row fields.
Provide witnesses and use `repeat split; lia` for constraints.

### Witness construction for admissibility
Use `{[store_loc := LitDict [...]; trace_loc := LitList []]}` for the
sigma witness. `store_loc`/`trace_loc` come from the shared defs file.

### Generic layer structure
- L0: admissibility + exit coverage
- L1: spec consistency (use gen_table_total)
- L2: helper lemmas (store_inv_lookup, gen_preserves_inv)
- L3: invariant preservation + frame soundness

### L2 induction pattern (applies to all contracts)

`store_inv_lookup` — exact proof (works for every contract):
```coq
induction store_d as [|kv rest IH]; intros k row Hinv Hlook; simpl in *.
- discriminate.
- destruct kv as [k0 v0].
  destruct Hinv as [Hfst Hrest].
  destruct k0 as [| | s | | | | | | | |]; simpl in *;
    try (apply (IH k row Hrest Hlook)).
  destruct (String.eqb k s) eqn:E.
  + injection Hlook as Hlook. subst v0. exact Hfst.
  + apply (IH k row Hrest Hlook).
```

`gen_preserves_inv_0` — structure (witnesses differ per contract):
```coq
intros <all premises>.
induction store_d as [|kv rest IH]; intros Hlook Hrow Hpos Hge Hinv; simpl in *.
- discriminate.
- destruct kv as [k0 v0].
  destruct Hinv as [Hfst Hrest].
  destruct k0 as [| | s | | | | | | | |]; simpl in *;
    try (split; [exact Hfst | apply (IH ... Hrest)]).
  destruct (String.eqb sku s) eqn:E.
  + (* same key: update preserves the row invariant by delta arithmetic *)
    ...
  + apply (IH ... Hrest).
```

---

## Part III — Implementation-lowering WP refinement

Proving `wp_exn (lowered_body args) (λ _, True)` for programs lowered by
`specsaver.lower.impl_lower` / `theory_lower`.  Distilled from the five
completed lowering proofs (AddOne, Dict, ComputeAvailable, Withdraw,
FullRestock).

### The Core Loop

Every lowered program is a nested `Let` chain over the two-cell heap
(`store_loc`, `trace_loc`).  Walk the chain one Let at a time:

```
wp_bind_item (LetCtx x body)   →  evaluate RHS  →  wp_let  →  cbn
```

**CRITICAL: the LetCtx body must carry substitutions from ALL prior steps.**
After `wp_let` on variable `x`, every later LetCtx body replaces `Var "x"`
with the produced value (e.g. `Val (LitDict store_d_vals)`,
`Val (row_of oh rs rp)`, `Val (LitInt oh)`).

```coq
(* WRONG — body still has Var "row" after row was substituted: *)
iApply (wp_bind_item (LetCtx "oh" (
  Let "res" (Call "dict_lookup_str" [Val (LitString "reserved"); Var "row"]) (
  BinOp SubOp (Var "oh") (Var "res"))))); [reflexivity|].

(* RIGHT — substituted value in place: *)
iApply (wp_bind_item (LetCtx "oh" (
  Let "res" (Call "dict_lookup_str"
               [Val (LitString "reserved"); Val (row_of oh rs rp)]) (
  BinOp SubOp (Var "oh") (Var "res"))))); [reflexivity|].
```

Get this wrong and `iApply (wp_bind_item ...)` fails with
`cannot apply WPE ?Goal {{ bind_post ... }}`.

### Required helper lemmas (copy into each file)

Library calls resolve through `wp_call` with a `FunSpec` from the `FunCtx`.
Three lemmas cover the current fragment:

```coq
Hypothesis Hen_lookup : fun_entries "dict_lookup_str" = Some (FunSpec ...).
Hypothesis Hen_insert : fun_entries "dict_insert_str" = Some (FunSpec ...).
Hypothesis Hen_row_of : fun_entries "row_of" = Some (FunSpec ...).

Lemma wp_dict_lookup (key : string) (d : list (sn_val * sn_val)) (Phi : Result -> iProp Σ) :
  (∀ v, ⌜dict_lookup_str key d = Some v⌝ -∗ Phi (RVal v)%I) -∗
  WPE (Call "dict_lookup_str" [Val (LitString key); Val (LitDict d)]) {{ Phi }}.

Lemma wp_dict_insert (key : string) (v : sn_val) (d : list (sn_val * sn_val)) (Phi : Result -> iProp Σ) :
  Phi (RVal (LitDict (dict_insert_str key v d)))%I -∗
  WPE (Call "dict_insert_str" [Val (LitString key); Val v; Val (LitDict d)]) {{ Phi }}.

Lemma wp_row_of (oh rs rp : Z) (Phi : Result -> iProp Σ) :
  Phi (RVal (row_of oh rs rp))%I -∗
  WPE (Call "row_of" [Val (LitInt oh); Val (LitInt rs); Val (LitInt rp)]) {{ Phi }}.
```

Their proofs are identical across files — see `coq/DictLowering.v` or
`coq/FullRestockLowering.v` (wp_call + iDestruct + inversion + subst +
iApply "Hpost").

### Step templates

**Load**
```coq
iApply (wp_bind_item (LetCtx "store_d" BODY)); [reflexivity|].
iApply (wp_load with "Hstore").
iNext. iIntros "Hstore".
iApply wp_let.
iNext. cbn.
```

**dict_lookup_str Call**
```coq
iApply (wp_bind_item (LetCtx "row" BODY)); [reflexivity|].
iApply wp_dict_lookup.
iIntros (v). iDestruct 1 as %Hdv.
(* if the row is known from a hypothesis: *)
assert (Some (row_of oh rs rp) = Some v) by congruence.
inversion H. subst v.
iApply wp_let.
iNext. cbn.
```

For field lookups into a concrete row (on_hand/reserved/reorder_point):
```coq
iApply wp_dict_lookup.
iIntros (v1). iDestruct 1 as %Hdv1.
cbn [dict_lookup_str] in Hdv1.   (* reduce the recursive lookup *)
inversion Hdv1. subst v1.
iApply wp_let.
iNext. cbn.
```

**If with EqOp on LitDict vs LitUnit (null check)**
`binop_eval EqOp (LitDict _) LitUnit = LitBool false` (kernel-level —
do NOT expect LitUnit as before).

```coq
iApply (wp_bind_item (IfCtx RAISE_BRANCH ELSE_BRANCH)); [reflexivity|].
iApply wp_binop.
iNext. cbn [binop_eval].
iApply wp_value.
cbn [binop_eval].
iApply wp_if_false.   (* dict is never LitUnit *)
iNext.
```

If the value COULD be LitUnit, case-split:
```coq
destruct (x <? y)%Z eqn:Hlt.
- rewrite Hlt. iApply wp_if_true. iNext. ...
- rewrite Hlt. iApply wp_if_false. iNext. ...
```

**BinOp with one unevaluated operand — type discipline**

- `BinOpLCtx op (v2 : sn_val)` — evaluate the LEFT operand; `v2` is the
  ALREADY-EVALUATED right operand.  Pass the raw `sn_val`
  (e.g. `(LitInt qty)`), **NOT** `Val (LitInt qty)` (that's `sn_expr`).
- `BinOpRCtx op (e1 : sn_expr)` — evaluate the RIGHT operand; `e1` is the
  unevaluated left expression.

```coq
iApply (wp_bind_item (BinOpLCtx AddOp (LitInt qty))); [reflexivity|].
iApply wp_dict_lookup.            (* evaluate the left Call *)
...
iApply wp_binop.                  (* now both operands are values *)
iNext. cbn [binop_eval].
iApply wp_value.
iApply wp_let.
iNext. cbn.
```

**dict_insert_str Call**
```coq
iApply (wp_bind_item (LetCtx "new_store" BODY)); [reflexivity|].
iApply wp_dict_insert.
iApply wp_let.
iNext. cbn.
```

**row_of Call (all args must be values or Vars)**
The lowerer hoists non-value args to `Let "_row_arg_N"` bindings.  Each
hoisted binding is its own LetCtx step:

```coq
iApply (wp_bind_item (LetCtx "_row_arg_0" BODY)); [reflexivity|].
(* ... evaluate the hoisted expression ... *)
iApply wp_let. iNext. cbn.
(* once all three are bound: *)
iApply wp_row_of.
iApply wp_let.
iNext. cbn.
```

**Store**
```coq
iApply (wp_bind_item (LetCtx "_" BODY)); [reflexivity|].
iApply (wp_store with "Hstore").
iNext. iIntros "Hstore".
iApply wp_let.
iNext. cbn.
```

**Final value**
```coq
iApply wp_value.
(* if an outer Let's bind_post still needs resolving: *)
iApply wp_let.
iNext. cbn.
iApply wp_value.
done.
```

### Pitfalls (each cost hours)

1. **Spurious wp_let.**  Each `wp_bind_item (LetCtx x _)` needs EXACTLY ONE
   `iApply wp_let` to resolve its bind_post.  Count: one per Let, applied
   after the RHS's value is produced.  An extra `iApply wp_let` after
   `wp_dict_lookup` fails with `cannot apply` because that bind_post was
   already consumed.

2. **`BinOpLCtx` needs `sn_val`.**  `(BinOpLCtx AddOp (Val (LitInt qty)))`
   fails — `(Val ...)` is `sn_expr`.  Use `(BinOpLCtx AddOp (LitInt qty))`.

3. **Missing final wp_let.**  After the update chain produces `Val LitUnit`
   for its inner `Let "_"`, the OUTER `Let "_"` (whose body is the return
   receipt) still needs `iApply wp_let; iNext. cbn; iApply wp_value; done.`
   Forgetting it leaves `done` with a bind_post goal —
   `No applicable tactic`.

4. **LitDict / row_of as Call arguments.**  `wp_dict_lookup`'s pattern is
   `[Val (LitString k); Val (LitDict d)]`.  If the goal has
   `Val (row_of oh rs rp)`, first `cbn [row_of]` to expose the `LitDict`
   before `iApply wp_dict_lookup`.

5. **Equality assert for row lookups.**
   `rewrite Hlookup in Hdv` fails when the goal doesn't mention
   `row_of oh rs rp` syntactically.  Use:
   ```coq
   assert (Some (row_of oh rs rp) = Some v) by congruence.
   inversion H. subst v.
   ```

6. **`iDestruct` patterns.**  `[Heq [Hdv Hr]]` fails on
   `exists k d v, vs = [...] /\ dict_lookup_str k d = Some v /\ r = v`.
   Use `[Heq Hr]` for a 2-conjunct tail, or destructure manually:
   ```coq
   iDestruct "Hpure" as %Hpure.
   destruct Hpure as [k' [d' [v' [Heq [Hdv Hr]]]]].
   inversion Heq. subst k' d'. subst v'.
   ```

### Reference proofs (canonical examples)

- `coq/AddOneLowering.v` — pure Let + BinOp (2 Qed)
- `coq/DictLowering.v` — Load + 2 dict lookups (3 Qed)
- `coq/ComputeAvailableLowering.v` — Load + 3 lookups + BinOp SubOp (3 Qed)
- `coq/WithdrawLowering.v` — If/LtOp + Raise + BinOp SubOp (2 Qed)
- `coq/FullRestockLowering.v` — nested Lets, If/Raise, 2 Loads, 5 Calls,
  BinOp, dict_insert, Store (4 Qed) — the canonical full example
