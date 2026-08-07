From iris.proofmode Require Import proofmode.
From iris.base_logic.lib Require Import gen_heap.
Require Import SnakeletExnLang SnakeletExnWp.
Require Import SpecPrelude.

(** Lowering the inventory [release] operation as a stateful opaque spec.

    Same two-cell heap model as reserve: store_loc (products dict) and
    trace_loc (event log).  Release subtracts from reserved:
      reserved' = reserved - quantity
    with the pre-condition that reserved >= quantity (so the subtraction
    is non-negative, preserving the invariant).
*)

Section release_lowering.
Context `{FC : FunCtx}.

Definition store_loc : loc := Loc 1%positive.
Definition trace_loc : loc := Loc 2%positive.

Definition row_of (oh rs rp : Z) : sn_val :=
  LitDict [(LitString "on_hand", LitInt oh);
           (LitString "reserved", LitInt rs);
           (LitString "reorder_point", LitInt rp)].

Definition product_inv (v : sn_val) : Prop :=
  exists oh rs rp,
    v = row_of oh rs rp /\ (rs >= 0)%Z /\ (rs <= oh)%Z.

Fixpoint store_inv (kvs : list (sn_val * sn_val)) : Prop :=
  match kvs with
  | [] => True
  | (_, v) :: rest => product_inv v /\ store_inv rest
  end.

(* ---------------------------------------------------------------- *)
(* The release spec.                                                 *)
(* ---------------------------------------------------------------- *)

Definition release_pre (sku : string) (qty : Z)
    (sigma : sn_state) (vs : list sn_val) : Prop :=
  exists store_d oh rs rp,
    vs = [LitString sku; LitInt qty] /\
    sigma !! store_loc = Some (LitDict store_d) /\
    dict_lookup_str sku store_d = Some (row_of oh rs rp) /\
    (qty > 0)%Z /\ (rs >= qty)%Z.

Definition release_post (sku : string) (qty : Z)
    (sigma : sn_state) (vs : list sn_val) (r : Result)
    (ups : cell_updates) : Prop :=
  exists store_d oh rs rp,
    vs = [LitString sku; LitInt qty] /\
    sigma !! store_loc = Some (LitDict store_d) /\
    dict_lookup_str sku store_d = Some (row_of oh rs rp) /\
    r = RVal (LitInt rs) /\
    ups = [(store_loc,
            LitDict (dict_insert_str sku (row_of oh (rs - qty) rp) store_d))].

(* The release transition preserves the store invariant: subtracting
   from reserved keeps it non-negative and <= on_hand. *)
Lemma release_preserves_inv_single : forall sku qty store_d oh rs rp,
  dict_lookup_str sku store_d = Some (row_of oh rs rp) ->
  product_inv (row_of oh rs rp) ->
  (qty > 0)%Z ->
  (rs >= qty)%Z ->
  store_inv store_d ->
  store_inv (dict_insert_str sku (row_of oh (rs - qty) rp) store_d).
Proof.
  induction store_d as [|kv rest IH]; intros oh rs rp Hlook Hprod Hpos Hge Hinv;
    simpl in Hlook |- *.
  - discriminate.
  - destruct kv as [k0 v0].
    destruct Hinv as [Hfst Hrest].
    destruct k0 as [| | s | | | | | | | | |]; simpl in *;
      try (split; [exact Hfst | apply (IH oh rs rp Hlook Hprod Hpos Hge Hrest)]).
    destruct (String.eqb sku s) eqn:E.
    + apply String.eqb_eq in E. subst s.
      injection Hlook as Hlook. subst v0.
      split; [|exact Hrest].
      destruct Hprod as [o [r [p [Heq [Hr Hlo]]]]].
      injection Heq as Ho Hrs Hrp. subst o r p.
      exists oh, (rs - qty)%Z, rp.
      split; [reflexivity|]. split; lia.
    + split; [exact Hfst|].
      apply (IH oh rs rp Hlook Hprod Hpos Hge Hrest).
Qed.

(* ---------------------------------------------------------------- *)
(* The release table and its totality obligation.                    *)
(* ---------------------------------------------------------------- *)

Definition release_pre_t (sigma : sn_state) (vs : list sn_val) : Prop :=
  exists sku qty, release_pre sku qty sigma vs.

Definition release_post_t (sigma : sn_state) (vs : list sn_val)
    (r : Result) (ups : cell_updates) : Prop :=
  exists sku qty, release_post sku qty sigma vs r ups.

Definition release_table (f : string) : option fun_entry :=
  if String.eqb f "release" then Some (FunSpecS release_pre_t release_post_t)
  else None.

Lemma release_table_total_pure : forall f pre post vs,
  release_table f = Some (FunSpec pre post) ->
  pre vs -> exists v, post vs v.
Proof.
  intros f pre post vs Hfe _. unfold release_table in Hfe.
  destruct (String.eqb f "release"); discriminate.
Qed.

Lemma release_table_total : forall f pre post vs sigma,
  release_table f = Some (FunSpecS pre post) ->
  pre sigma vs ->
  exists r ups, post sigma vs r ups /\ updates_dom_in sigma ups.
Proof.
  intros f pre post vs sigma Hfe Hpre. unfold release_table in Hfe.
  destruct (String.eqb f "release") eqn:E; [|discriminate].
  injection Hfe as Heq; subst pre post.
  destruct Hpre as [sku [qty Hpre]].
  destruct Hpre as [store_d [oh [rs [rp [Hvs [Hcell [Hlook [Hpos Hge]]]]]]]].
  exists (RVal (LitInt rs)),
    [(store_loc,
      LitDict (dict_insert_str sku (row_of oh (rs - qty) rp) store_d))].
  split.
  - exists sku, qty, store_d, oh, rs, rp. auto.
  - unfold updates_dom_in. constructor; [|constructor].
    simpl. rewrite Hcell. eexists. reflexivity.
Qed.

#[global] Instance release_fun_ctx : FunCtx :=
  {| fun_entries := release_table;
     fun_specs_total := release_table_total_pure;
     fun_specsS_total := release_table_total |}.

End release_lowering.
