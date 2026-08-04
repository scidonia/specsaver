From iris.proofmode Require Import proofmode.
From iris.base_logic.lib Require Import gen_heap.
Require Import SnakeletExnLang SnakeletExnWp.
Require Import SpecPrelude.

(** Phase 3: lowered multi-call dict program with subscript-style access.

    Python:                               SnakeletExn:
      row = dict_lookup_str(sku, store_d)   Let "row"   (dict_lookup_str sku   store_d)
      on_hand = row["on_hand"]              Let "oh"    (dict_lookup_str "on_hand" row)
      reserved = row["reserved"]             Let "res"   (dict_lookup_str "reserved" row)
      return on_hand - reserved             BinOp SubOp (Var "oh") (Var "res")

    Proved against a stateful FunSpecS. *)

Section compute_available_lowering.
Context `{FC : FunCtx}.
Context `{!snakeletExn_heapGS_gen hlc Σ}.

Definition store_loc : loc := Loc 1%positive.

Definition row_of (oh rs rp : Z) : sn_val :=
  LitDict [(LitString "on_hand", LitInt oh);
           (LitString "reserved", LitInt rs);
           (LitString "reorder_point", LitInt rp)].

Hypothesis Hen_lookup : fun_entries "dict_lookup_str" =
  Some (FunSpec
    (fun vs => exists k d, vs = [LitString k; LitDict d])
    (fun vs r => exists k d v, vs = [LitString k; LitDict d] /\
               dict_lookup_str k d = Some v /\ r = v)).

(* lowered program *)
Definition compute_available_body (sku : string) : sn_expr :=
  Let "store_d" (Load (Val (LitLoc store_loc))) (
  Let "row"  (Call "dict_lookup_str" [Val (LitString sku); Var "store_d"]) (
  Let "oh"   (Call "dict_lookup_str" [Val (LitString "on_hand"); Var "row"]) (
  Let "res"  (Call "dict_lookup_str" [Val (LitString "reserved"); Var "row"]) (
    BinOp SubOp (Var "oh") (Var "res")
  )))).

(* FunSpecS contract *)
Definition compute_available_pre (sigma : sn_state) (vs : list sn_val) : Prop :=
  exists sku store_d oh rs rp,
    vs = [LitString sku] /\
    sigma !! store_loc = Some (LitDict store_d) /\
    dict_lookup_str sku store_d = Some (row_of oh rs rp).

Definition compute_available_post (sigma : sn_state) (vs : list sn_val)
    (r : Result) (ups : cell_updates) : Prop :=
  exists sku store_d oh rs rp,
    vs = [LitString sku] /\
    sigma !! store_loc = Some (LitDict store_d) /\
    dict_lookup_str sku store_d = Some (row_of oh rs rp) /\
    r = RVal (LitInt (oh - rs)%Z).

Definition compute_table (f : string) : option fun_entry :=
  if String.eqb f "compute_available" then
    Some (FunSpecS compute_available_pre compute_available_post)
  else None.

Lemma compute_table_total : forall f pre post vs sigma,
  compute_table f = Some (FunSpecS pre post) ->
  pre sigma vs ->
  exists r ups, post sigma vs r ups /\ updates_dom_in sigma ups.
Proof.
  intros f pre post vs sigma Hfe Hpre.
  unfold compute_table in Hfe.
  destruct (String.eqb f "compute_available") eqn:E; try discriminate.
  apply String.eqb_eq in E. subst f.
  inversion Hfe. subst pre post.
  destruct Hpre as [sku' [store_d' [oh' [rs' [rp' [Hvs [Hcell Hlook]]]]]]].
  subst vs.
  exists (RVal (LitInt (oh' - rs')%Z)), [].
  split.
  - exists sku', store_d', oh', rs', rp'.
    repeat split; auto.
  - unfold updates_dom_in. constructor.
Qed.

(* wp_dict_lookup helper *)
Lemma wp_dict_lookup (key : string) (d : list (sn_val * sn_val)) (Phi : Result -> iProp Σ) :
  (∀ v, ⌜dict_lookup_str key d = Some v⌝ -∗ Phi (RVal v)%I) -∗
  WPE (Call "dict_lookup_str" [Val (LitString key); Val (LitDict d)]) {{ Phi }}.
Proof.
  iIntros "Hpost".
  iApply (wp_call "dict_lookup_str"
    (fun vs => exists k d0, vs = [LitString k; LitDict d0])
    (fun vs r => exists k d0 v, vs = [LitString k; LitDict d0] /\
               dict_lookup_str k d0 = Some v /\ r = v)
    [LitString key; LitDict d] Phi).
  { exact Hen_lookup. }
  { exists key, d. eauto. }
  iNext. iIntros (v). iIntros "Hpure".
  iDestruct "Hpure" as %Hpure.
  destruct Hpure as [k' [d' [v' [Heq [Hdv Hr]]]]].
  inversion Heq. subst k' d'.
  subst v'.
  iApply "Hpost". iPureIntro. exact Hdv.
Qed.

(** WP refinement proof. *)
Lemma compute_available_refines (sku : string) (store_d_vals : list (sn_val * sn_val))
    (oh rs rp : Z) :
  dict_lookup_str sku store_d_vals = Some (row_of oh rs rp) ->
  pointsto store_loc (DfracOwn 1) (LitDict store_d_vals) -∗
  wp_exn (compute_available_body sku) (λ r,
    ⌜r = RVal (LitInt (oh - rs)%Z)⌝)%I.
Proof.
  iIntros (Hlookup) "Hstore".
  unfold compute_available_body.

  (* Step 1: Load the store dict *)
  iApply (wp_bind_item (LetCtx "store_d" (
    Let "row" (Call "dict_lookup_str" [Val (LitString sku); Var "store_d"]) (
    Let "oh" (Call "dict_lookup_str" [Val (LitString "on_hand"); Var "row"]) (
    Let "res" (Call "dict_lookup_str" [Val (LitString "reserved"); Var "row"]) (
    BinOp SubOp (Var "oh") (Var "res"))))))); [reflexivity|].
  iApply (wp_load with "Hstore").
  iNext. iIntros "Hstore".
  iApply wp_let.
  iNext. cbn.

  (* Step 2: dict_lookup_str sku store_d_vals *)
  iApply (wp_bind_item (LetCtx "row" (
    Let "oh" (Call "dict_lookup_str" [Val (LitString "on_hand"); Var "row"]) (
    Let "res" (Call "dict_lookup_str" [Val (LitString "reserved"); Var "row"]) (
    BinOp SubOp (Var "oh") (Var "res")))))); [reflexivity|].
  iApply wp_dict_lookup.
  iIntros (v). iDestruct 1 as %Hdv.
  assert (Some (row_of oh rs rp) = Some v) by congruence.
  inversion H. subst v.
  iApply wp_let.
  iNext. cbn.

  (* Step 3: dict_lookup_str "on_hand" row_of *
     After subst, Var "row" → Val (row_of oh rs rp). *)
  iApply (wp_bind_item (LetCtx "oh" (
    Let "res" (Call "dict_lookup_str" [Val (LitString "reserved");
               Val (row_of oh rs rp)]) (
    BinOp SubOp (Var "oh") (Var "res"))))); [reflexivity|].
  iApply wp_dict_lookup.
  iIntros (v1). iDestruct 1 as %Hdv1.
  simpl in Hdv1. inversion Hdv1. subst v1.
  iApply wp_let.
  iNext. cbn.

  (* Step 4: dict_lookup_str "reserved" row_of *)
  iApply (wp_bind_item (LetCtx "res" (
    BinOp SubOp (Val (LitInt oh)) (Var "res")))); [reflexivity|].
  cbn [row_of].
  iApply wp_dict_lookup.
  iIntros (v2). iDestruct 1 as %Hdv2.
  simpl in Hdv2. inversion Hdv2. subst v2.
  iApply wp_let.
  iNext. cbn.

  (* Step 5: BinOp SubOp oh res *)
  iApply wp_binop.
  iNext.
  iApply wp_value.
  iPureIntro. reflexivity.
Qed.

End compute_available_lowering.
