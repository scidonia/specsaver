From stdpp Require Import gmap.
Require Import SnakeletExnLang SpecPrelude.

(** Partial evaluator for SnakeletExn: one step at a time.

    Instead of trying to fully evaluate a program in one go (which
    Coq's Eval compute can't handle for deep nesting), we define a
    functional one-step evaluator and chain steps explicitly.

    The one-step relation [prim_step] is a Prop (relation).  This
    module provides a functional version [eval_step] that computes
    the next expression given the current expression and heap.

    Usage:
      Compute (eval_step e sigma).        (* one step *)
      Compute (eval_step_n 10 e sigma).   (* up to 10 steps *)
*)

(* ── heap model (association list for Eval-computability) ── *)
Definition heap_alist := list (loc * sn_val).

Definition loc_eqb (l1 l2 : loc) : bool :=
  bool_decide (l1 = l2).

Definition heap_lookup (l : loc) (h : heap_alist) : option sn_val :=
  match List.find (fun '(k, _) => loc_eqb k l) h with
  | Some (_, v) => Some v
  | None => None
  end.

Definition heap_insert (l : loc) (v : sn_val) (h : heap_alist) : heap_alist :=
  (l, v) :: List.filter (fun '(k, _) => negb (loc_eqb k l)) h.

(* ── value check ── *)
Definition is_val (e : sn_expr) : option sn_val :=
  match e with
  | Val v => Some v
  | _ => None
  end.

(* ── one-step evaluator ── *)

(* Pure step: evaluate a pure expression (no heap access) *)
Definition eval_pure_step (e : sn_expr) : option sn_expr :=
  match e with
  | Let x (Val v) e2 => Some (subst x v e2)
  | Let x (BinOp op (Val v1) (Val v2)) e2 =>
      (* Evaluate the BinOp first, then the Let *)
      Some (Let x (Val (binop_eval op v1 v2)) e2)
  | BinOp op (Val v1) (Val v2) => Some (Val (binop_eval op v1 v2))
  | If (Val (LitBool true)) e1 e2 => Some e1
  | If (Val (LitBool false)) e1 e2 => Some e2
  | _ => None
  end.

(* Head step: evaluate a heap-touching or calling expression *)
Definition eval_head_step (e : sn_expr) (h : heap_alist)
    : option (sn_expr * heap_alist) :=
  match e with
  | Let x (Load (Val (LitLoc l))) e2 =>
      (* Load then Let: load the value, then substitute *)
      match heap_lookup l h with
      | Some v => Some (Let x (Val v) e2, h)
      | None => Some (Raise (Val (LitExn "KeyError" LitUnit)), h)
      end
  | Let x (Store (Val (LitLoc l)) (Val v)) e2 =>
      (* Store then Let: store the value, then continue *)
      Some (Let x (Val LitUnit) e2, heap_insert l v h)
  | Let x (Alloc (Val v)) e2 =>
      (* Alloc then Let *)
      let l := Loc (Pos.of_nat (length h + 1)) in
      Some (Let x (Val (LitLoc l)) e2, heap_insert l v h)
  | Load (Val (LitLoc l)) =>
      match heap_lookup l h with
      | Some v => Some (Val v, h)
      | None => Some (Raise (Val (LitExn "KeyError" LitUnit)), h)
      end
  | Store (Val (LitLoc l)) (Val v) =>
      Some (Val LitUnit, heap_insert l v h)
  | Alloc (Val v) =>
      let l := Loc (Pos.of_nat (length h + 1)) in
      Some (Val (LitLoc l), heap_insert l v h)
  | Call fname args =>
      (* All args must be values *)
      let fix collect (es : list sn_expr) (acc : list sn_val)
          : option (list sn_val) :=
        match es with
        | [] => Some (List.rev acc)
        | Val v :: es' => collect es' (v :: acc)
        | _ => None
        end in
      match collect args [] with
      | Some vs =>
          match fname with
          | "dict_lookup_str" =>
              match vs with
              | [LitString k; LitDict d] =>
                  match dict_lookup_str k d with
                  | Some v => Some (Val v, h)
                  | None => Some (Val LitUnit, h)
                  end
              | _ => Some (Raise (Val (LitExn "TypeError"
                    (LitString "dict_lookup_str-args"))), h)
              end
          | "dict_insert_str" =>
              match vs with
              | [LitString k; v; LitDict d] =>
                  Some (Val (LitDict (dict_insert_str k v d)), h)
              | _ => Some (Raise (Val (LitExn "TypeError"
                    (LitString "dict_insert_str-args"))), h)
              end
          | "row_of" =>
              match vs with
              | [LitInt oh; LitInt rs; LitInt rp] =>
                  Some (Val (LitDict
                    [(LitString "on_hand", LitInt oh);
                     (LitString "reserved", LitInt rs);
                     (LitString "reorder_point", LitInt rp)]), h)
              | _ => Some (Raise (Val (LitExn "TypeError"
                    (LitString "row_of-args"))), h)
              end
          | _ => Some (Raise (Val (LitExn "NotImplemented"
                (LitString ("call:" ++ fname)))), h)
          end
      | None => None  (* args not all values *)
      end
  | Raise (Val (LitExn lbl pay)) =>
      Some (Raise (Val (LitExn lbl pay)), h)  (* already a value *)
  | _ => None
  end.

(* Context decomposition: find the redex in an evaluation context *)
Fixpoint decompose (e : sn_expr) : option (sn_ectx_item * sn_expr) :=
  match e with
  | Let x e1 e2 =>
      match is_val e1 with
      | Some v => None  (* Let is a head step *)
      | None =>
          match decompose e1 with
          | Some (Ki, e') => Some (Ki, e')  (* propagate *)
          | None => None
          end
      end
  | BinOp op e1 e2 =>
      match is_val e1 with
      | Some v1 =>
          match is_val e2 with
          | Some v2 => None  (* BinOp on values is a head step *)
          | None =>
              match decompose e2 with
              | Some (Ki, e') => Some (BinOpRCtx op e1, e')
              | None => None
              end
          end
      | None =>
          match decompose e1 with
          | Some (Ki, e') => Some (BinOpLCtx op (match e2 with Val v => v | _ => LitUnit end), e')
          | None => None
          end
      end
  | If c e1 e2 =>
      match is_val c with
      | Some _ => None  (* If is a head step *)
      | None =>
          match decompose c with
          | Some (Ki, e') => Some (IfCtx e1 e2, e')
          | None => None
          end
      end
  | Raise e1 =>
      match is_val e1 with
      | Some _ => None  (* Raise is a head step *)
      | None =>
          match decompose e1 with
          | Some (Ki, e') => Some (RaiseCtx, e')
          | None => None
          end
      end
  | Try body x handler =>
      match is_val body with
      | Some _ => None  (* Try on value is a head step *)
      | None =>
          match decompose body with
          | Some (Ki, e') => Some (TryCtx x handler, e')
          | None => None
          end
      end
  | _ => None
  end.

(* Recompose: fill a context *)
Definition recompose (Ki : sn_ectx_item) (e : sn_expr) : sn_expr :=
  fill_item Ki e.

(* One step of evaluation *)
Definition eval_step (e : sn_expr) (h : heap_alist)
    : option (sn_expr * heap_alist) :=
  match eval_pure_step e with
  | Some e' => Some (e', h)
  | None =>
      match eval_head_step e h with
      | Some (e', h') => Some (e', h')
      | None =>
          (* Try to decompose and step the redex *)
          match decompose e with
          | Some (Ki, redex) =>
              match eval_pure_step redex with
              | Some e' => Some (recompose Ki e', h)
              | None =>
                  match eval_head_step redex h with
                  | Some (e', h') => Some (recompose Ki e', h')
                  | None => None
                  end
              end
          | None => None
          end
      end
  end.

(* Multi-step evaluation *)
Fixpoint eval_step_n (n : nat) (e : sn_expr) (h : heap_alist)
    : option (sn_expr * heap_alist) :=
  match n with
  | O => Some (e, h)
  | S n' =>
      match eval_step e h with
      | Some (e', h') =>
          match is_val e' with
          | Some v => Some (Val v, h')  (* reached a value *)
          | None => eval_step_n n' e' h'
          end
      | None => Some (e, h)  (* stuck — return current state *)
      end
  end.

(* ── convenience ── *)
Definition run_steps (n : nat) (h : heap_alist) (e : sn_expr)
    : option (sn_expr * heap_alist) :=
  eval_step_n n e h.
