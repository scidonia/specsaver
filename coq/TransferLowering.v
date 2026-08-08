From iris.proofmode Require Import proofmode.
From iris.base_logic.lib Require Import gen_heap.
Require Import SnakeletExnLang SnakeletExnWp.
Require Import SpecPrelude.

(** Lowering the bank [transfer] operation as a stateful opaque spec.

    Multi-delta: source.balance -= amount, target.balance += amount.
    Two exception arms: InsufficientFundsError, CurrencyMismatchError.
    Invariant: all balances >= 0.
*)

Section transfer_lowering.
Context `{FC : FunCtx}.

Definition store_loc : loc := Loc 1%positive.
Definition trace_loc : loc := Loc 2%positive.

Definition row_of (balance : Z) (currency : string) : sn_val :=
  LitDict [(LitString "balance", LitInt balance);
           (LitString "currency", LitString currency)].

Fixpoint store_inv (kvs : list (sn_val * sn_val)) : Prop :=
  match kvs with
  | [] => True
  | (_, v) :: rest =>
      (exists b c, v = row_of b c /\ (b >= 0)%Z) /\ store_inv rest
  end.

(* ── Transfer spec ── *)

Definition transfer_pre (src_id tgt_id : string) (amt : Z)
    (sigma : sn_state) (vs : list sn_val) : Prop :=
  exists store_d src_b tgt_b src_c tgt_c,
    vs = [LitString src_id; LitString tgt_id; LitInt amt] /\
    sigma !! store_loc = Some (LitDict store_d) /\
    dict_lookup_str src_id store_d = Some (row_of src_b src_c) /\
    dict_lookup_str tgt_id store_d = Some (row_of tgt_b tgt_c) /\
    (amt > 0)%Z /\ (src_b >= amt)%Z /\ (src_c = tgt_c)%Z.

Definition transfer_post (src_id tgt_id : string) (amt : Z)
    (sigma : sn_state) (vs : list sn_val) (r : Result)
    (ups : cell_updates) : Prop :=
  exists store_d src_b tgt_b src_c tgt_c,
    vs = [LitString src_id; LitString tgt_id; LitInt amt] /\
    sigma !! store_loc = Some (LitDict store_d) /\
    dict_lookup_str src_id store_d = Some (row_of src_b src_c) /\
    dict_lookup_str tgt_id store_d = Some (row_of tgt_b tgt_c) /\
    r = RVal (LitInt tgt_b) /\
    ups = [(store_loc,
            LitDict (dict_insert_str tgt_id (row_of (tgt_b + amt) tgt_c)
              (dict_insert_str src_id (row_of (src_b - amt) src_c)
                 store_d)))].

(* ── Totality and FunCtx ── *)

Definition transfer_pre_t (sigma : sn_state) (vs : list sn_val) : Prop :=
  exists src_id tgt_id amt, transfer_pre src_id tgt_id amt sigma vs.

Definition transfer_post_t (sigma : sn_state) (vs : list sn_val)
    (r : Result) (ups : cell_updates) : Prop :=
  exists src_id tgt_id amt, transfer_post src_id tgt_id amt sigma vs r ups.

Definition transfer_table (f : string) : option fun_entry :=
  if String.eqb f "transfer" then Some (FunSpecS transfer_pre_t transfer_post_t)
  else None.

Lemma transfer_table_total_pure : forall f pre post vs,
  transfer_table f = Some (FunSpec pre post) ->
  pre vs -> exists v, post vs v.
Proof.
  intros f pre post vs Hfe _. unfold transfer_table in Hfe.
  destruct (String.eqb f "transfer"); discriminate.
Qed.

Lemma transfer_table_total : forall f pre post vs sigma,
  transfer_table f = Some (FunSpecS pre post) ->
  pre sigma vs ->
  exists r ups, post sigma vs r ups /\ updates_dom_in sigma ups.
Proof.
  intros f pre post vs sigma Hfe Hpre. unfold transfer_table in Hfe.
  destruct (String.eqb f "transfer") eqn:E; [|discriminate].
  injection Hfe as Heq; subst pre post.
  destruct Hpre as [src_id [tgt_id [amt Hpre]]].
  destruct Hpre as [store_d [src_b [tgt_b [src_c [tgt_c
    [Hvs [Hcell [Hsrc [Htgt [Hpos [Hge Hcurr]]]]]]]]]]].
  exists (RVal (LitInt tgt_b)),
    [(store_loc,
      LitDict (dict_insert_str tgt_id (row_of (tgt_b + amt) tgt_c)
                (dict_insert_str src_id (row_of (src_b - amt) src_c)
                   store_d)))].
  split.
  - exists src_id, tgt_id, amt, store_d, src_b, tgt_b, src_c, tgt_c. repeat split; auto.
  - unfold updates_dom_in. constructor; [|constructor].
    simpl. rewrite Hcell. eexists. reflexivity.
Qed.

#[global] Instance transfer_fun_ctx : FunCtx :=
  {| fun_entries := transfer_table;
     fun_specs_total := transfer_table_total_pure;
     fun_specsS_total := transfer_table_total |}.

End transfer_lowering.
