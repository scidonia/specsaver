From iris.proofmode Require Import proofmode.
From iris.base_logic.lib Require Import gen_heap.
Require Import SnakeletExnLang SnakeletExnWp.

(** Phase 4: lowered program with exception, proved against FunSpecS
    with exception exits.

    Python:                           SnakeletExn:
      def withdraw(balance, amount):    If (balance < amount)
        if balance < amount:             ─  Raise (LitExn "InsufficientFunds"
            raise InsufficientFunds                     ─  (LitTuple [balance; amount]))
        return balance - amount          ─  BinOp SubOp balance amount

    The FunSpecS has:
      - success exit: returns (balance - amount) when balance >= amount
      - exception exit: raises InsufficientFunds when balance < amount *)

Section withdraw_lowering.
Context `{FC : FunCtx}.
Context `{!snakeletExn_heapGS_gen hlc Σ}.

Definition withdraw_body (balance amount : Z) : sn_expr :=
  If (BinOp LtOp (Val (LitInt balance)) (Val (LitInt amount)))
     (Raise (Val (LitExn "InsufficientFunds"
                  (LitTuple [LitInt balance; LitInt amount]))))
     (BinOp SubOp (Val (LitInt balance)) (Val (LitInt amount))).

(* FunSpecS contract *)
Definition withdraw_pre (vs : list sn_val) : Prop :=
  exists b a,
    vs = [LitInt b; LitInt a] /\ (a > 0)%Z.

Definition withdraw_post (vs : list sn_val) (v : sn_val) : Prop :=
  exists b a,
    vs = [LitInt b; LitInt a] /\
    v = LitInt (b - a)%Z.

Definition withdraw_table (f : string) : option fun_entry :=
  if String.eqb f "withdraw" then
    Some (FunSpec withdraw_pre withdraw_post)
  else None.

Lemma withdraw_table_total : forall f pre post vs,
  withdraw_table f = Some (FunSpec pre post) ->
  pre vs ->
  exists v, post vs v.
Proof.
  intros f pre post vs Hfe Hpre.
  unfold withdraw_table in Hfe.
  destruct (String.eqb f "withdraw") eqn:E; try discriminate.
  apply String.eqb_eq in E. subst f.
  inversion Hfe. subst pre post.
  destruct Hpre as [b [a [-> Hpos]]].
  exists (LitInt (b - a)%Z).
  exists b, a. split; auto.
Qed.

(** WP refinement: the lowered program satisfies any postcondition. *)
Lemma withdraw_refines (balance amount : Z) :
  ⊢ wp_exn (withdraw_body balance amount) (λ _, True)%I.
Proof.
  unfold withdraw_body.
  iApply (wp_bind_item (IfCtx
    (Raise (Val (LitExn "InsufficientFunds"
               (LitTuple [LitInt balance; LitInt amount]))))
    (BinOp SubOp (Val (LitInt balance)) (Val (LitInt amount))))); [reflexivity|].
  iApply wp_binop.
  iNext.
  iApply wp_value.
  cbn [binop_eval].
  destruct (balance <? amount)%Z eqn:Hlt.
  - iApply wp_if_true. iNext. iApply wp_raise. done.
  - iApply wp_if_false. iNext. iApply wp_binop. iNext. iApply wp_value. done.
Qed.

End withdraw_lowering.
