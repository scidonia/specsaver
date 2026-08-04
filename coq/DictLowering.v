From iris.proofmode Require Import proofmode.
From iris.base_logic.lib Require Import gen_heap.
Require Import SnakeletExnLang SnakeletExnWp.
Require Import SpecPrelude.

(** Phase 2: lowered dict-operation program, proved against a FunSpecS.

    Python:                           SnakeletExn lowered form:
      def read_reserved(sku):           Let "store_d" (Load store_loc) (
        store_d = load_store()          ─  Let "row" (dict_lookup_str sku store_d) (
        row = dict_lookup_str(sku,        ─    Let "reserved"
                    ─ store_d)                        ─  (dict_lookup_str "reserved" row) (
        return dict_lookup_str(              ─      Var "reserved")))
                  ─  "reserved", row)

    Proved against a stateful FunSpecS that asserts the store lookup
    succeeds and the return value equals the reserved count. *)

Section dict_lowering.
Context `{FC : FunCtx}.
Context `{!snakeletExn_heapGS_gen hlc Σ}.

Definition store_loc : loc := Loc 1%positive.

Definition row_of (oh rs rp : Z) : sn_val :=
  LitDict [(LitString "on_hand", LitInt oh);
           (LitString "reserved", LitInt rs);
           (LitString "reorder_point", LitInt rp)].

(* Context provides the dict_lookup_str spec *)
Hypothesis Hen_lookup : fun_entries "dict_lookup_str" =
  Some (FunSpec
    (fun vs => exists k d, vs = [LitString k; LitDict d])
    (fun vs r => exists k d v, vs = [LitString k; LitDict d] /\
               dict_lookup_str k d = Some v /\ r = v)).

(* ── the lowered program (arguments substituted) ── *)
Definition read_reserved_body (sku : string) : sn_expr :=
  Let "store_d" (Load (Val (LitLoc store_loc))) (
  Let "row"     (Call "dict_lookup_str"
                      [Val (LitString sku); Var "store_d"]) (
  Let "res"     (Call "dict_lookup_str"
                      [Val (LitString "reserved"); Var "row"]) (
    Var "res"
  ))).

(* ── the FunSpecS contract ── *)
Definition read_reserved_pre (sigma : sn_state) (vs : list sn_val) : Prop :=
  exists sku store_d oh rs rp,
    vs = [LitString sku] /\
    sigma !! store_loc = Some (LitDict store_d) /\
    dict_lookup_str sku store_d = Some (row_of (oh) (rs) (rp)).

Definition read_reserved_post (sigma : sn_state) (vs : list sn_val)
    (r : Result) (ups : cell_updates) : Prop :=
  exists sku store_d oh rs rp,
    vs = [LitString sku] /\
    sigma !! store_loc = Some (LitDict store_d) /\
    dict_lookup_str sku store_d = Some (row_of (oh) (rs) (rp)) /\
    r = RVal (LitInt rs).

Definition read_table (f : string) : option fun_entry :=
  if String.eqb f "read_reserved" then
    Some (FunSpecS read_reserved_pre read_reserved_post)
  else None.

Lemma read_table_total : forall f pre post vs sigma,
  read_table f = Some (FunSpecS pre post) ->
  pre sigma vs ->
  exists r ups, post sigma vs r ups /\ updates_dom_in sigma ups.
Proof.
  intros f pre post vs sigma Hfe Hpre.
  unfold read_table in Hfe.
  destruct (String.eqb f "read_reserved") eqn:E; try discriminate.
  apply String.eqb_eq in E. subst f.
  inversion Hfe. subst pre post.
  destruct Hpre as [sku' [store_d' [oh' [rs' [rp' [Hvs [Hcell Hlook]]]]]]].
  subst vs.
  exists (RVal (LitInt rs')), [].
  split.
  - exists sku', store_d', oh', rs', rp'.
    repeat split; auto.
  - unfold updates_dom_in. constructor.
Qed.

(* ── wp_dict_lookup lemma ── *)
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

(** WP refinement: the lowered program satisfies the postcondition.
    The heap must contain the store dict. *)
Lemma read_reserved_refines (sku : string) (store_d_vals : list (sn_val * sn_val))
    (oh rs rp : Z) :
  dict_lookup_str sku store_d_vals = Some (row_of oh rs rp) ->
  pointsto store_loc (DfracOwn 1) (LitDict store_d_vals) -∗
  wp_exn (read_reserved_body sku) (λ r,
    ⌜r = RVal (LitInt rs)⌝)%I.
Proof.
  iIntros (Hlookup) "Hstore".
  unfold read_reserved_body.
  iApply (wp_bind_item (LetCtx "store_d" (
    Let "row" (Call "dict_lookup_str" [Val (LitString sku); Var "store_d"]) (
    Let "res" (Call "dict_lookup_str" [Val (LitString "reserved"); Var "row"]) (Var "res"))))); [reflexivity|].
  iApply (wp_load with "Hstore").
  iNext. iIntros "Hstore".
  iApply wp_let.
  iNext.
  iApply (wp_bind_item (LetCtx "row" (
    Let "res" (Call "dict_lookup_str" [Val (LitString "reserved"); Var "row"]) (Var "res")))); [reflexivity|].
  iApply wp_dict_lookup.
  iIntros (v). iDestruct 1 as %Hdv.
  assert (Some (row_of oh rs rp) = Some v) by congruence.
  inversion H. subst v.
  iApply wp_let.
  iNext.
  iApply (wp_bind_item (LetCtx "res" (Var "res"))); [reflexivity|].
  iApply wp_dict_lookup.
  iIntros (v2). iDestruct 1 as %Hdv2.
  simpl in Hdv2.
  inversion Hdv2. subst v2.
  iApply wp_let.
  iNext.
  iApply wp_value.
  iPureIntro. reflexivity.
Qed.

End dict_lowering.