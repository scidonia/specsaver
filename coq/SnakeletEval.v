From stdpp Require Import gmap.
Require Import SnakeletExnLang.

(** Extended pure evaluator with Try/Raise support.

    The evaluator returns [option sn_expr]:
    - [Some (Val v)]   — the expression reduced to a value.
    - [Some (Raise (Val exn))] — the expression raised an uncaught exception.
    - [None]           — fuel ran out or the expression is stuck.

    Exception propagation follows the SnakeletExnLang semantics:
    - [Raise (Val v)] is a stuck terminal (irreducible).
    - A [Raise] propagates through [Let], [BinOp] arguments, and [If]
      conditions.
    - [Try (Val v) x h] skips the handler (success path).
    - [Try (Raise (Val exn)) x h] catches and substitutes the handler.
*)

Fixpoint eval_pure (fuel : nat) (e : sn_expr) : option sn_expr :=
  match fuel with
  | O => None
  | S fuel' =>
      match to_val e with
      | Some v => Some e
      | None =>
          match e with
          (* ── Let ── *)
          | Let x e1 e2 =>
              match eval_pure fuel' e1 with
              | Some (Val v) => eval_pure fuel' (subst x v e2)
              | Some (Raise (Val _) as r) => Some r  (* propagate *)
              | _ => None
              end

          (* ── BinOp ── *)
          | BinOp op (Val v1) (Val v2) =>
              Some (Val (binop_eval op v1 v2))
          | BinOp op e1 e2 =>
              match eval_pure fuel' e1 with
              | Some (Val v1) =>
                  match eval_pure fuel' e2 with
                  | Some (Val v2) =>
                      Some (Val (binop_eval op v1 v2))
                  | Some (Raise (Val _) as r) => Some r
                  | _ => None
                  end
              | Some (Raise (Val _) as r) => Some r
              | _ => None
              end

          (* ── If ── *)
          | If (Val (LitBool true)) e1 e2 =>
              eval_pure fuel' e1
          | If (Val (LitBool false)) e1 e2 =>
              eval_pure fuel' e2
          | If c e1 e2 =>
              match eval_pure fuel' c with
              | Some (Val (LitBool true)) => eval_pure fuel' e1
              | Some (Val (LitBool false)) => eval_pure fuel' e2
              | Some (Raise (Val _) as r) => Some r
              | _ => None
              end

          (* ── Raise ── *)
          | Raise (Val v) =>
              Some (Raise (Val v))  (* stuck terminal, irreducible *)
          | Raise e' =>
              match eval_pure fuel' e' with
              | Some (Val v) => Some (Raise (Val v))
              | _ => None
              end

          (* ── Try ── *)
          | Try (Val v) _x _h =>
              Some (Val v)  (* normal completion, handler skipped *)
          | Try (Raise (Val (LitExn lbl pay))) x h =>
              eval_pure fuel' (subst x (LitExn lbl pay) h)  (* catch *)
          | Try e' x h =>
              match eval_pure fuel' e' with
              | Some (Val v) => Some (Val v)
              | Some (Raise (Val (LitExn lbl pay))) =>
                  eval_pure fuel' (subst x (LitExn lbl pay) h)
              | _ => None
              end

          | _ => None
          end
      end
  end.
