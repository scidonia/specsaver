From iris.proofmode Require Import proofmode.
From iris.base_logic.lib Require Import gen_heap.
Require Import SnakeletExnLang SnakeletExnWp SnakeletExnTactics.
Require Import SpecPrelude.

Section restock_lowering.
Context `{FC : FunCtx}.
Context `{!snakeletExn_heapGS_gen hlc Σ}.

Definition store_loc : loc := Loc 1%positive.
Definition trace_loc : loc := Loc 2%positive.

Definition row_of (oh rs rp : Z) : sn_val :=
  LitDict [(LitString "on_hand", LitInt oh);
           (LitString "reserved", LitInt rs);
           (LitString "reorder_point", LitInt rp)].

Hypothesis Hen_lookup : fun_entries "dict_lookup_str" =
  Some (FunSpec
    (fun vs => exists k d, vs = [LitString k; LitDict d])
    (fun vs r => exists k d v, vs = [LitString k; LitDict d] /\
               dict_lookup_str k d = Some v /\ r = v)).

Hypothesis Hen_insert : fun_entries "dict_insert_str" =
  Some (FunSpec
    (fun vs => exists k v d, vs = [LitString k; v; LitDict d])
    (fun vs r => exists k v d, vs = [LitString k; v; LitDict d] /\
               r = LitDict (dict_insert_str k v d))).

Hypothesis Hen_row_of : fun_entries "row_of" =
  Some (FunSpec
    (fun vs => exists oh rs rp, vs = [LitInt oh; LitInt rs; LitInt rp])
    (fun vs result => exists oh rs rp, vs = [LitInt oh; LitInt rs; LitInt rp] /\
               result = row_of oh rs rp)).

(* Lowered restock body *)
Definition restock_body (sku : string) (qty : Z) : sn_expr :=
  Let "row" (Let "store_d" (Load (Val (LitLoc store_loc)))
               (Call "dict_lookup_str" [Val (LitString sku); Var "store_d"])) (
  If (BinOp EqOp (Var "row") (Val LitUnit))
     (Raise (Val (LitExn "ProductNotFoundError" LitUnit)))
     (Let "_" (Let "store_d" (Load (Val (LitLoc store_loc))) (
        Let "old_row" (Call "dict_lookup_str" [Val (LitString sku); Var "store_d"]) (
        Let "new_row" (
          Let "_row_arg_0" (BinOp AddOp
            (Call "dict_lookup_str" [Val (LitString "on_hand"); Var "old_row"])
            (Val (LitInt qty))) (
          Let "_row_arg_1" (Call "dict_lookup_str" [Val (LitString "reserved"); Var "old_row"]) (
          Let "_row_arg_2" (Call "dict_lookup_str" [Val (LitString "reorder_point"); Var "old_row"]) (
          Call "row_of" [Var "_row_arg_0"; Var "_row_arg_1"; Var "_row_arg_2"])))) (
        Let "new_store" (Call "dict_insert_str"
          [Val (LitString sku); Var "new_row"; Var "store_d"]) (
        Let "_" (Store (Val (LitLoc store_loc)) (Var "new_store"))
          (Val LitUnit))))))
     (Val (LitDict
       [(LitString "0", LitString sku);
        (LitString "1", LitInt qty)]))
  )).

(* helper lemmas *)
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

Lemma wp_dict_insert (key : string) (v : sn_val) (d : list (sn_val * sn_val)) (Phi : Result -> iProp Σ) :
  Phi (RVal (LitDict (dict_insert_str key v d)))%I -∗
  WPE (Call "dict_insert_str" [Val (LitString key); Val v; Val (LitDict d)]) {{ Phi }}.
Proof.
  iIntros "Hpost".
  iApply (wp_call "dict_insert_str"
    (fun vs => exists k v' d0, vs = [LitString k; v'; LitDict d0])
    (fun vs r => exists k v' d0, vs = [LitString k; v'; LitDict d0] /\
               r = LitDict (dict_insert_str k v' d0))
    [LitString key; v; LitDict d] Phi).
  { exact Hen_insert. }
  { exists key, v, d. eauto. }
  iNext. iIntros (result). iIntros "Hpure".
  iDestruct "Hpure" as %Hpure.
  destruct Hpure as [k' [v' [d' [Heq Hr]]]].
  injection Heq as Hk Hv Hd. subst k' v' d'.
  rewrite Hr.
  iApply "Hpost".
Qed.

Lemma wp_row_of (oh rs rp : Z) (Phi : Result -> iProp Σ) :
  Phi (RVal (row_of oh rs rp))%I -∗
  WPE (Call "row_of" [Val (LitInt oh); Val (LitInt rs); Val (LitInt rp)]) {{ Phi }}.
Proof.
  iIntros "Hpost".
  iApply (wp_call "row_of"
    (fun vs => exists oh' rs' rp', vs = [LitInt oh'; LitInt rs'; LitInt rp'])
    (fun vs result => exists oh' rs' rp', vs = [LitInt oh'; LitInt rs'; LitInt rp'] /\
               result = row_of oh' rs' rp')
    [LitInt oh; LitInt rs; LitInt rp] Phi).
  { exact Hen_row_of. }
  { exists oh, rs, rp. eauto. }
  iNext. iIntros (result). iIntros "Hpure".
  iDestruct "Hpure" as %Hpure.
  destruct Hpure as [o' [s' [r' [Heq Hr]]]].
  injection Heq as Ho Hs Hr2. subst o' s' r'.
  rewrite Hr.
  iApply "Hpost".
Qed.

(** WP refinement: full proof via sequential wp_bind_item steps,
    following the ComputeAvailableLowering pattern with per-step
    substitutions. *)
Lemma restock_refines (sku : string) (qty : Z)
    (store_d_vals : list (sn_val * sn_val)) (oh rs rp : Z) :
  dict_lookup_str sku store_d_vals = Some (row_of oh rs rp) ->
  pointsto store_loc (DfracOwn 1) (LitDict store_d_vals) -∗
  wp_exn (restock_body sku qty) (λ _, True)%I.
Proof.
  iIntros (Hlookup) "Hstore".
  unfold restock_body.

  iApply (wp_bind_item (LetCtx "row" (If (BinOp EqOp (Var "row") (Val LitUnit)) (Raise (Val (LitExn "ProductNotFoundError" LitUnit))) (Let "_" (Let "store_d" (Load (Val (LitLoc store_loc))) (Let "old_row" (Call "dict_lookup_str" [Val (LitString sku); Var "store_d"]) (Let "new_row" (Let "_row_arg_0" (BinOp AddOp (Call "dict_lookup_str" [Val (LitString "on_hand"); Var "old_row"]) (Val (LitInt qty))) (Let "_row_arg_1" (Call "dict_lookup_str" [Val (LitString "reserved"); Var "old_row"]) (Let "_row_arg_2" (Call "dict_lookup_str" [Val (LitString "reorder_point"); Var "old_row"]) (Call "row_of" [Var "_row_arg_0"; Var "_row_arg_1"; Var "_row_arg_2"])))) (Let "new_store" (Call "dict_insert_str" [Val (LitString sku); Var "new_row"; Var "store_d"]) (Let "_" (Store (Val (LitLoc store_loc)) (Var "new_store")) (Val LitUnit)))))) (Val (LitDict [(LitString "0", LitString sku); (LitString "1", LitInt qty)])))))); [reflexivity|].
  iApply (wp_bind_item (LetCtx "store_d" (Call "dict_lookup_str" [Val (LitString sku); Var "store_d"]))); [reflexivity|].
  iApply (wp_load with "Hstore").
  iNext. iIntros "Hstore".
  iApply wp_let.
  iNext. cbn.
  iApply wp_dict_lookup.
  iIntros (v). iDestruct 1 as %Hdv.
  assert (Some (row_of oh rs rp) = Some v) by congruence.
  inversion H. subst v.
  iApply wp_let.
  iNext. cbn.
  iApply (wp_bind_item (IfCtx (Raise (Val (LitExn "ProductNotFoundError" LitUnit))) (Let "_" (Let "store_d" (Load (Val (LitLoc store_loc))) (Let "old_row" (Call "dict_lookup_str" [Val (LitString sku); Var "store_d"]) (Let "new_row" (Let "_row_arg_0" (BinOp AddOp (Call "dict_lookup_str" [Val (LitString "on_hand"); Var "old_row"]) (Val (LitInt qty))) (Let "_row_arg_1" (Call "dict_lookup_str" [Val (LitString "reserved"); Var "old_row"]) (Let "_row_arg_2" (Call "dict_lookup_str" [Val (LitString "reorder_point"); Var "old_row"]) (Call "row_of" [Var "_row_arg_0"; Var "_row_arg_1"; Var "_row_arg_2"])))) (Let "new_store" (Call "dict_insert_str" [Val (LitString sku); Var "new_row"; Var "store_d"]) (Let "_" (Store (Val (LitLoc store_loc)) (Var "new_store")) (Val LitUnit)))))) (Val (LitDict [(LitString "0", LitString sku); (LitString "1", LitInt qty)]))))); [reflexivity|].
  iApply wp_binop.
  iNext. cbn [binop_eval].
  iApply wp_value.
  cbn [binop_eval].
  iApply wp_if_false.
  iNext.
  iApply (wp_bind_item (LetCtx "_" (Val (LitDict [(LitString "0", LitString sku); (LitString "1", LitInt qty)])))); [reflexivity|].
  iApply (wp_bind_item (LetCtx "store_d" (Let "old_row" (Call "dict_lookup_str" [Val (LitString sku); Var "store_d"]) (Let "new_row" (Let "_row_arg_0" (BinOp AddOp (Call "dict_lookup_str" [Val (LitString "on_hand"); Var "old_row"]) (Val (LitInt qty))) (Let "_row_arg_1" (Call "dict_lookup_str" [Val (LitString "reserved"); Var "old_row"]) (Let "_row_arg_2" (Call "dict_lookup_str" [Val (LitString "reorder_point"); Var "old_row"]) (Call "row_of" [Var "_row_arg_0"; Var "_row_arg_1"; Var "_row_arg_2"])))) (Let "new_store" (Call "dict_insert_str" [Val (LitString sku); Var "new_row"; Var "store_d"]) (Let "_" (Store (Val (LitLoc store_loc)) (Var "new_store")) (Val LitUnit))))))); [reflexivity|].
  iApply (wp_load with "Hstore").
  iNext. iIntros "Hstore".
  iApply wp_let.
  iNext. cbn.
  iApply (wp_bind_item (LetCtx "old_row" (Let "new_row" (Let "_row_arg_0" (BinOp AddOp (Call "dict_lookup_str" [Val (LitString "on_hand"); Var "old_row"]) (Val (LitInt qty))) (Let "_row_arg_1" (Call "dict_lookup_str" [Val (LitString "reserved"); Var "old_row"]) (Let "_row_arg_2" (Call "dict_lookup_str" [Val (LitString "reorder_point"); Var "old_row"]) (Call "row_of" [Var "_row_arg_0"; Var "_row_arg_1"; Var "_row_arg_2"])))) (Let "new_store" (Call "dict_insert_str" [Val (LitString sku); Var "new_row"; Val (LitDict store_d_vals)]) (Let "_" (Store (Val (LitLoc store_loc)) (Var "new_store")) (Val LitUnit)))))); [reflexivity|].
  iApply wp_dict_lookup.
  iIntros (v1). iDestruct 1 as %Hdv1.
  assert (Some (row_of oh rs rp) = Some v1) by congruence.
  inversion H0. subst v1.
  iApply wp_let.
  iNext. cbn.
  iApply (wp_bind_item (LetCtx "new_row" (Let "new_store" (Call "dict_insert_str" [Val (LitString sku); Var "new_row"; Val (LitDict store_d_vals)]) (Let "_" (Store (Val (LitLoc store_loc)) (Var "new_store")) (Val LitUnit))))); [reflexivity|].
  iApply (wp_bind_item (LetCtx "_row_arg_0" (Let "_row_arg_1" (Call "dict_lookup_str" [Val (LitString "reserved"); Val (row_of oh rs rp)]) (Let "_row_arg_2" (Call "dict_lookup_str" [Val (LitString "reorder_point"); Val (row_of oh rs rp)]) (Call "row_of" [Var "_row_arg_0"; Var "_row_arg_1"; Var "_row_arg_2"]))))); [reflexivity|].
  iApply (wp_bind_item (BinOpLCtx AddOp (LitInt qty))); [reflexivity|].
  iApply wp_dict_lookup.
  iIntros (v2). iDestruct 1 as %Hdv2.
  cbn [dict_lookup_str] in Hdv2. inversion Hdv2. subst v2.
  iApply wp_binop.
  iNext. cbn [binop_eval].
  iApply wp_value.
  iApply wp_let.
  iNext. cbn.
  iApply (wp_bind_item (LetCtx "_row_arg_1" (Let "_row_arg_2" (Call "dict_lookup_str" [Val (LitString "reorder_point"); Val (row_of oh rs rp)]) (Call "row_of" [Val (LitInt (oh + qty)%Z); Var "_row_arg_1"; Var "_row_arg_2"])))); [reflexivity|].
  iApply wp_dict_lookup.
  iIntros (v3). iDestruct 1 as %Hdv3.
  cbn [dict_lookup_str] in Hdv3. inversion Hdv3. subst v3.
  iApply wp_let.
  iNext. cbn.
  iApply (wp_bind_item (LetCtx "_row_arg_2" (Call "row_of" [Val (LitInt (oh + qty)%Z); Val (LitInt rs); Var "_row_arg_2"]))); [reflexivity|].
  iApply wp_dict_lookup.
  iIntros (v4). iDestruct 1 as %Hdv4.
  cbn [dict_lookup_str] in Hdv4. inversion Hdv4. subst v4.
  iApply wp_let.
  iNext. cbn.
  iApply wp_row_of.
  iApply wp_let.
  iNext. cbn.
  iApply (wp_bind_item (LetCtx "new_store" (Let "_" (Store (Val (LitLoc store_loc)) (Var "new_store")) (Val LitUnit)))); [reflexivity|].
  iApply wp_dict_insert.
  iApply wp_let.
  iNext. cbn.
  iApply (wp_bind_item (LetCtx "_" (Val LitUnit))); [reflexivity|].
  iApply (wp_store with "Hstore").
  iNext. iIntros "Hstore".
  iApply wp_let.
  iNext. cbn.
  iApply wp_value.
  iApply wp_let.
  iNext. cbn.
  iApply wp_value.
  done.
Qed.

End restock_lowering.
