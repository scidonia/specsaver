From iris.proofmode Require Import proofmode.
From iris.base_logic.lib Require Import gen_heap.
Require Import SnakeletExnLang SnakeletExnWp.

(** Phase 1: lowered pure-Python function, proven against a FunSpecS.

    Python source:                     SnakeletExn lowered form:
      def add_one(x):                    Let "y" (BinOp AddOp (Var "x")
      ─   y = x + 1                              (Val (LitInt 1)))
      ─   return y                         (Var "y")

    The contract: add_one(x) returns x+1.  Proved by WP reasoning. *)

Section add_one_lowering.
Context `{FC : FunCtx}.
Context `{!snakeletExn_heapGS_gen hlc Σ}.

(* ── the lowered program (arguments substituted) ── *)
Definition add_one_body (x : Z) : sn_expr :=
  Let "y" (BinOp AddOp (Val (LitInt x)) (Val (LitInt 1)))
         (Var "y").

(* ── the FunSpecS contract ── *)
Definition add_one_pre (vs : list sn_val) : Prop :=
  exists x,
    vs = [LitInt x].

Definition add_one_post (vs : list sn_val) (v : sn_val) : Prop :=
  exists x,
    vs = [LitInt x] /\
    v = LitInt (x + 1)%Z.

Definition add_one_table (f : string) : option fun_entry :=
  if String.eqb f "add_one" then
    Some (FunSpec add_one_pre add_one_post)
  else None.

Lemma add_one_table_total_pure : forall vs,
  add_one_pre vs -> exists v, add_one_post vs v.
Proof.
  intros vs Hpre.
  destruct Hpre as [x Hvs]. subst vs.
  exists (LitInt (x + 1)%Z).
  unfold add_one_post. exists x. auto.
Qed.

Lemma add_one_refines_spec (x : Z) :
  ⊢ wp_exn (add_one_body x) (λ _, True)%I.
Proof.
  unfold add_one_body.
  iApply (wp_bind_item (LetCtx "y" (Var "y"))); [reflexivity|].
  iApply wp_binop.
  iNext.
  iApply wp_value.
  iApply wp_let.
  iNext.
  iApply wp_value.
  eauto.
Qed.

End add_one_lowering.
