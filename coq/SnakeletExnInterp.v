From stdpp Require Import gmap.
Require Import SnakeletExnLang SpecPrelude.

(** A definitional interpreter for SnakeletExn programs.
    Produces a Result (RVal v | RExn lbl payload) — the same type
    used by the WP calculus.  This is the trusted reference
    implementation: any BDD test or partial evaluator can be
    validated against it. *)

(* ── environment ── *)
Definition interp_env := list (string * sn_val).

Definition env_lookup (x : string) (env : interp_env) : option sn_val :=
  match List.find (fun '(k, _) => String.eqb k x) env with
  | Some (_, v) => Some v
  | None => None
  end.

(* ── heap model ── *)
Record interp_state := {
  heap : gmap loc sn_val;
  trace : list (string * sn_val);  (* event channel *)
}.

(* ── the interpreter ── *)
Fixpoint interp (fuel : nat) (st : interp_state) (env : interp_env)
    (e : sn_expr) {struct fuel} : option (Result * interp_state) :=
  match fuel with
  | O => None
  | S fuel' =>
      match e with
      | Val v => Some (RVal v, st)

      | Var x =>
          match env_lookup x env with
          | Some v => Some (RVal v, st)
          | None => Some (RExn "UnboundVar" (LitString x), st)
          end

      | Let x e1 e2 =>
          match interp fuel' st env e1 with
          | Some (RVal v, st') =>
              interp fuel' st' ((x, v) :: env) e2
          | Some (RExn lbl pay, st') => Some (RExn lbl pay, st')
          | None => None
          end

      | BinOp op e1 e2 =>
          match interp fuel' st env e1 with
          | Some (RVal v1, st') =>
              match interp fuel' st' env e2 with
              | Some (RVal v2, st'') =>
                  (* Type-error check: arithmetic ops on non-numeric
                     operands produce TypeError, not LitUnit. *)
                  match op with
                  | AddOp | SubOp | MulOp | DivOp | ModOp =>
                      match v1, v2 with
                      | LitInt _, LitInt _
                      | LitInt _, LitFloat _
                      | LitFloat _, LitInt _
                      | LitFloat _, LitFloat _ =>
                          Some (RVal (binop_eval op v1 v2), st'')
                      | _, _ =>
                          Some (RExn "TypeError"
                                (LitString
                                  ("unsupported operand: " ++
                                   "arithmetic on non-numeric")), st'')
                      end
                  | EqOp | NeOp =>
                      (* Equality is total — any two values can be
                         compared (mismatched types are unequal). *)
                      Some (RVal (binop_eval op v1 v2), st'')
                  | LtOp | LeOp | GtOp | GeOp =>
                      match v1, v2 with
                      | LitInt _, LitInt _
                      | LitInt _, LitFloat _
                      | LitFloat _, LitInt _
                      | LitFloat _, LitFloat _ =>
                          Some (RVal (binop_eval op v1 v2), st'')
                      | _, _ =>
                          Some (RExn "TypeError"
                                (LitString
                                  ("unsupported operand: " ++
                                   "comparison on non-numeric")), st'')
                      end
                  | _ =>
                      Some (RVal (binop_eval op v1 v2), st'')
                  end
              | Some (RExn lbl pay, st'') => Some (RExn lbl pay, st'')
              | None => None
              end
          | Some (RExn lbl pay, st') => Some (RExn lbl pay, st')
          | None => None
          end

      | If c e1 e2 =>
          match interp fuel' st env c with
          | Some (RVal (LitBool true), st') => interp fuel' st' env e1
          | Some (RVal (LitBool false), st') => interp fuel' st' env e2
          | Some (RVal v, st') =>
              Some (RExn "TypeError" (LitString "if-condition-not-bool"), st')
          | Some (RExn lbl pay, st') => Some (RExn lbl pay, st')
          | None => None
          end

      | Raise payload_expr =>
          match interp fuel' st env payload_expr with
          | Some (RVal (LitExn lbl pay), st') =>
              Some (RExn lbl pay, st')
          | Some (RVal v, st') =>
              Some (RExn "RuntimeError" v, st')
          | Some (RExn lbl pay, st') => Some (RExn lbl pay, st')
          | None => None
          end

      | Try body x handler =>
          match interp fuel' st env body with
          | Some (RVal v, st') => Some (RVal v, st')
          | Some (RExn lbl pay, st') =>
              interp fuel' st' ((x, LitExn lbl pay) :: env) handler
          | None => None
          end

      | Load loc_expr =>
          match interp fuel' st env loc_expr with
          | Some (RVal (LitLoc l), st') =>
              match st.(heap) !! l with
              | Some v => Some (RVal v, st')
              | None => Some (RExn "KeyError" (LitString "unallocated-loc"), st')
              end
          | Some (RVal v, st') =>
              Some (RExn "TypeError" (LitString "load-non-loc"), st')
          | Some (RExn lbl pay, st') => Some (RExn lbl pay, st')
          | None => None
          end

      | Store loc_expr val_expr =>
          match interp fuel' st env loc_expr with
          | Some (RVal (LitLoc l), st') =>
              match interp fuel' st' env val_expr with
              | Some (RVal v, st'') =>
                  Some (RVal LitUnit,
                        {| heap := <[l := v]> st''.(heap);
                           trace := st''.(trace) |})
              | Some (RExn lbl pay, st'') => Some (RExn lbl pay, st'')
              | None => None
              end
          | Some (RVal v, st') =>
              Some (RExn "TypeError" (LitString "store-non-loc"), st')
          | Some (RExn lbl pay, st') => Some (RExn lbl pay, st')
          | None => None
          end

      | Alloc val_expr =>
          match interp fuel' st env val_expr with
          | Some (RVal v, st') =>
              let l := Loc (Pos.of_nat (size st'.(heap) + 1)) in
              Some (RVal (LitLoc l),
                    {| heap := <[l := v]> st'.(heap);
                       trace := st'.(trace) |})
          | Some (RExn lbl pay, st') => Some (RExn lbl pay, st')
          | None => None
          end

      | Call fname args =>
          (* Evaluate all args left-to-right, collecting values.
             Uses the outer fuel — each interp call decreases it. *)
          let fix eval_args (es : list sn_expr) (st0 : interp_state)
              (env0 : interp_env) (acc : list sn_val)
              : option (list sn_val * interp_state) :=
            match es with
            | [] => Some (List.rev acc, st0)
            | e0 :: es' =>
                match interp fuel' st0 env0 e0 with
                | Some (RVal v, st') =>
                    eval_args es' st' env0 (v :: acc)
                | Some (RExn lbl pay, st') => None
                | None => None
                end
            end in
          match eval_args args st env [] with
          | Some (vs, st') =>
              (* Library function dispatch *)
              match fname with
              | "dict_lookup_str" =>
                  match vs with
                  | [LitString k; LitDict d] =>
                      match dict_lookup_str k d with
                      | Some v => Some (RVal v, st')
                      | None => Some (RVal LitUnit, st')
                      end
                  | _ => Some (RExn "TypeError"
                                 (LitString "dict_lookup_str-args"), st')
                  end
              | "dict_insert_str" =>
                  match vs with
                  | [LitString k; v; LitDict d] =>
                      Some (RVal (LitDict (dict_insert_str k v d)), st')
                  | _ => Some (RExn "TypeError"
                                 (LitString "dict_insert_str-args"), st')
                  end
              | "row_of" =>
                  match vs with
                  | [LitInt oh; LitInt rs; LitInt rp] =>
                      Some (RVal (LitDict
                        [(LitString "on_hand", LitInt oh);
                         (LitString "reserved", LitInt rs);
                         (LitString "reorder_point", LitInt rp)]), st')
                  | _ => Some (RExn "TypeError"
                                 (LitString "row_of-args"), st')
                  end
              | _ =>
                  (* Unknown function — check fun_entries *)
                  Some (RExn "NotImplemented"
                           (LitString ("call:" ++ fname)), st')
              end
          | None => None
          end

      | While _ _ =>
          Some (RExn "NotImplemented" (LitString "while"), st)

      | For _ _ _ =>
          Some (RExn "NotImplemented" (LitString "for"), st)
      end
  end.

(* ── convenience wrapper ── *)
Definition run (fuel : nat) (initial_heap : gmap loc sn_val)
    (env : interp_env) (e : sn_expr) : option Result :=
  match interp fuel {| heap := initial_heap; trace := [] |} env e with
  | Some (r, _) => Some r
  | None => None
  end.

(* ── sanity checks ── *)
(* add_one: Let "y" (BinOp AddOp (Var "x") (Val (LitInt 1))) (Var "y") *)
Example interp_add_one :
  run 100 ∅ [("x", LitInt 5)]
    (Let "y" (BinOp AddOp (Var "x") (Val (LitInt 1))) (Var "y"))
  = Some (RVal (LitInt 6)).
Proof. reflexivity. Qed.

(* restock success path: simplified — just the dict ops *)
Example interp_restock_simplified :
  run 500
    (<[Loc 1%positive := LitDict
      [(LitString "SKU1",
        LitDict [(LitString "on_hand", LitInt 10);
                 (LitString "reserved", LitInt 3);
                 (LitString "reorder_point", LitInt 5)])]]> ∅)
    [("sku", LitString "SKU1"); ("quantity", LitInt 20);
     ("store_loc", LitLoc (Loc 1%positive))]
    (Let "store_d" (Load (Var "store_loc")) (
     Let "old_row" (Call "dict_lookup_str"
                      [Val (LitString "SKU1"); Var "store_d"]) (
     Let "_row_arg_0" (BinOp AddOp
                        (Call "dict_lookup_str"
                          [Val (LitString "on_hand"); Var "old_row"])
                        (Var "quantity")) (
     Let "new_row" (Call "row_of"
                      [Var "_row_arg_0";
                       Call "dict_lookup_str"
                         [Val (LitString "reserved"); Var "old_row"];
                       Call "dict_lookup_str"
                         [Val (LitString "reorder_point"); Var "old_row"]]) (
     Let "new_store" (Call "dict_insert_str"
                        [Val (LitString "SKU1"); Var "new_row";
                         Var "store_d"]) (
     Let "_" (Store (Var "store_loc") (Var "new_store"))
         (Val (LitDict
           [(LitString "0", LitString "SKU1");
            (LitString "1", LitInt 20)]))
     ))))))
  = Some (RVal (LitDict
           [(LitString "0", LitString "SKU1");
            (LitString "1", LitInt 20)])).
Proof. reflexivity. Qed.
