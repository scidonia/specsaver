"""Emit Coq obligation files from a ContractInfo (v2).

v2 shape: multi-delta (nested inserts over distinct keys), multiple
exception arms, conjunctive `when` conditions, typed row fields
(int and string).  Every template is a shape proven by hand; the
friction inventory is baked into the script patterns.
"""

from __future__ import annotations

from specsaver.lower.introspect import ContractInfo, DeltaInfo, ExitInfo

_STORE_LOC = "store_loc"
_TRACE_LOC = "trace_loc"


def _is_int_expr(s: str, info: ContractInfo) -> bool:
    """Is every identifier in the expression int-typed (int field vars,
    the qty arg, or numeric literals)?"""
    import re as _re

    int_fields = {f for f, _t in info.row_fields if _t == "int"}
    qty = info.deltas[0].qty_arg
    int_vars = int_fields | {
        _field_var(f, k) for k in _keys(info) for f in int_fields
    }
    for tok in _re.split(r"[^A-Za-z0-9_]+", s):
        if not tok or tok.isdigit() or tok == qty:
            continue
        if tok in int_vars:
            continue
        return False
    return True


def _z(s: str, info: ContractInfo) -> str:
    """Wrap in %Z scope iff the expression is int-typed."""
    return f"({s})%Z" if _is_int_expr(s, info) else f"({s})"


_NEGATE = {"<": ">=", "<=": ">", ">": "<=", ">=": "<", "=": "<>", "<>": "="}


def avail_str(info: ContractInfo) -> str | None:
    """Success availability = ¬(∃i. when_i), with %Z scoping per clause."""
    if not info.exits:
        return None
    arms = []
    for ex in info.exits:
        negs = " \\/ ".join(
            _z(f"{lhs} {_NEGATE[o]} {r}", info) for lhs, o, r in ex.when_clauses
        )
        arms.append(f"({negs})")
    return " /\\ ".join(arms)


def _field_var(field: str, key: str) -> str:
    return f"{field}_{key}"


def _keys(info: ContractInfo) -> list[str]:
    keys: list[str] = []
    for d in info.deltas:
        if d.key_arg not in keys:
            keys.append(d.key_arg)
    return keys


def _row_fields(info: ContractInfo) -> list[str]:
    return [f for f, _ in info.row_fields]


def _lit(field: str, type_: str, var: str) -> str:
    return f'LitString {var}' if type_ == "str" else f'LitInt {var}'


def _row_ctor(info: ContractInfo) -> str:
    ints = " ".join(f for f, _t in info.row_fields if _t == "int")
    strs = " ".join(f for f, _t in info.row_fields if _t == "str")
    binders = []
    if ints:
        binders.append(f"({ints} : Z)")
    if strs:
        binders.append(f"({strs} : string)")
    pairs = ";\n           ".join(
        f'(LitString "{f}", {_lit(f, t, f)})' for f, t in info.row_fields
    )
    return f"""Definition row_of {' '.join(binders)} : sn_val :=
  LitDict [{pairs}]."""


def _row_call2(info: ContractInfo, values: dict[str, str]) -> str:
    args = []
    for f, _ in info.row_fields:
        args.append(f"({values[f]})")
    return f"(row_of {' '.join(args)})"


def _defaults(info: ContractInfo, key: str) -> dict[str, str]:
    return {f: _field_var(f, key) for f in _row_fields(info)}


def _row_inv(info: ContractInfo) -> str:
    fields = " ".join(_row_fields(info))
    clauses = []
    for f in info.non_neg:
        clauses.append(f"({f} >= 0)%Z")
    if info.invariant_le:
        small, big = info.invariant_le
        clauses.append(f"({small} <= {big})%Z")
    if not clauses:
        return ""
    conj = " /\\ ".join(clauses)
    return f"""Definition row_inv (v : sn_val) : Prop :=
  exists {fields},
    v = {_row_call2(info, {f: f for f in _row_fields(info)})} /\\ {conj}."""


def _store_inv() -> str:
    return """Fixpoint store_inv (kvs : list (sn_val * sn_val)) : Prop :=
  match kvs with
  | [] => True
  | (_, v) :: rest => row_inv v /\\ store_inv rest
  end."""


def _exist_vars(info: ContractInfo) -> str:
    parts = [f"{k}" for k in _keys(info)]
    parts.append("order")
    parts.append(info.deltas[0].qty_arg)
    parts.append("store_d")
    for k in _keys(info):
        parts.extend(_field_var(f, k) for f in _row_fields(info))
    return " ".join(parts)


def _exists_args(info: ContractInfo) -> str:
    """Same variables, comma-joined for the exists tactic (tuple form —
    space-separated witnesses do not unroll nested existentials)."""
    return ", ".join(_exist_vars(info).split())


def _vs_args(info: ContractInfo) -> str:
    parts = [f"LitString {k}" for k in _keys(info)]
    parts.append("LitString order")
    parts.append(f"LitInt {info.deltas[0].qty_arg}")
    return "; ".join(parts)


def _lookups(info: ContractInfo) -> str:
    lines = []
    for k in _keys(info):
        row = _row_call2(info, _defaults(info, k))
        lines.append(f"dict_lookup_str {k} store_d = Some {row}")
    return " /\\\n    ".join(lines)


def _scalar_props(info: ContractInfo) -> str:
    if not info.scalars:
        return "True"
    return " /\\ ".join(_z(f"{lhs} {o} {r}", info) for lhs, o, r in info.scalars)


def _pre(info: ContractInfo) -> str:
    return f"""Definition gen_pre (sigma : sn_state) (vs : list sn_val) : Prop :=
  exists {_exist_vars(info)},
    vs = [{_vs_args(info)}] /\\
    sigma !! {_STORE_LOC} = Some (LitDict store_d) /\\
    {_lookups(info)} /\\
    {_scalar_props(info)} /\\ ({avail_str(info) or "True"})."""


def _nested_insert(info: ContractInfo) -> str:
    expr = "store_d"
    for d in info.deltas:
        new_vals = _defaults(info, d.key_arg)
        qty = d.qty_arg
        new_vals[d.field] = (
            f"{_field_var(d.field, d.key_arg)} {d.op} {qty}"
            if d.op == "-" else f"{_field_var(d.field, d.key_arg)} {d.op} {qty}"
        )
        expr = (f"(dict_insert_str {d.key_arg} "
                f"{_row_call2(info, new_vals)} {expr})")
    return expr


def _post(info: ContractInfo) -> str:
    d0 = info.deltas[0]
    result_val = _field_var(d0.field, d0.key_arg)
    return f"""Definition gen_post (sigma : sn_state) (vs : list sn_val)
    (r : Result) (ups : cell_updates) : Prop :=
  exists {_exist_vars(info)},
    vs = [{_vs_args(info)}] /\\
    sigma !! {_STORE_LOC} = Some (LitDict store_d) /\\
    {_lookups(info)} /\\
    r = RVal (LitInt {result_val}) /\\
    ups = [({_STORE_LOC}, LitDict {_nested_insert(info)})]."""


def _exc_payload(info: ContractInfo, ex: ExitInfo) -> str:
    vals = []
    d0 = info.deltas[0]
    for p in ex.payload:
        if p in _keys(info):
            vals.append(f"LitString {p}")
        elif p == "order_id":
            vals.append("LitString order")
        elif p == d0.qty_arg:
            vals.append(f"LitInt {d0.qty_arg}")
        elif p == "available" and info.invariant_le:
            big, small = info.invariant_le[1], info.invariant_le[0]
            key = _keys(info)[0]
            vals.append(
                f"LitInt ({_field_var(big, key)} - {_field_var(small, key)})")
        elif p in _row_fields(info):
            vals.append(f"LitInt {_field_var(p, _keys(info)[0])}")
        else:
            vals.append("LitUnit")
    return "; ".join(vals) if vals else "LitUnit"


def _exc(info: ContractInfo) -> list[tuple[str, str, str]]:
    """One (name, pre, post) triple per exception arm."""
    arms = []
    for i, ex in enumerate(info.exits):
        name = f"gen_exc{i}_"
        clauses = " /\\\n    ".join(
            _z(f"{lhs} {o} {r}", info) for lhs, o, r in ex.when_clauses)
        pre = f"""Definition {name}pre (sigma : sn_state) (vs : list sn_val) : Prop :=
  exists {_exist_vars(info)},
    vs = [{_vs_args(info)}] /\\
    sigma !! {_STORE_LOC} = Some (LitDict store_d) /\\
    {_lookups(info)} /\\
    {clauses}."""
        post = f"""Definition {name}post (sigma : sn_state) (vs : list sn_val)
    (r : Result) (ups : cell_updates) : Prop :=
  exists {_exist_vars(info)},
    vs = [{_vs_args(info)}] /\\
    sigma !! {_STORE_LOC} = Some (LitDict store_d) /\\
    {_lookups(info)} /\\
    r = RExn "{ex.name}" (LitTuple [{_exc_payload(info, ex)}]) /\\ ups = []."""
        arms.append((name, pre, post))
    return arms


def _table(info: ContractInfo, arms: list) -> str:
    exc_arms = "".join(
        f'\n  else if String.eqb f "{info.name}_exc{i}" then\n'
        f'  Some (FunSpecS {n}pre {n}post)'
        for i, (n, _, _) in enumerate(arms)
    )
    return f"""Definition gen_table (f : string) : option fun_entry :=
  if String.eqb f "{info.name}" then Some (FunSpecS gen_pre gen_post){exc_arms}
  else None."""


def _destruct_pat(info: ContractInfo, hyps: list[str]) -> str:
    names = [*_keys(info), "order", info.deltas[0].qty_arg, "store_d"]
    for k in _keys(info):
        names.extend(_field_var(f, k) for f in _row_fields(info))
    for h in hyps:
        if h == "Hlook":
            names.extend(f"Hlook_{k}" for k in _keys(info))
        else:
            names.append(h)
    pat = names[-1]
    for n in reversed(names[:-1]):
        pat = f"[{n} {pat}]"
    return pat


def _totality(info: ContractInfo, arms: list) -> str:
    d0 = info.deltas[0]
    eqbs = ",\n           ".join(
        [f'(String.eqb f "{info.name}") eqn:E']
        + [f'(String.eqb f "{info.name}_exc{i}") eqn:E{i + 2}'
           for i in range(len(arms))]
    )
    # The success entry matches whenever the head eqb fires — both the
    # (E-true, Ei-true) and (E-true, Ei-false) branches are success, so
    # solve them all at once with a chained script.
    success_script = (
        f"injection Hfe as Heq; subst pre post; "
        f"destruct Hpre as "
        f"{_destruct_pat(info, ['Hvs', 'Hcell', 'Hlook', 'Hsc', 'Havail'])}; "
        f"exists (RVal (LitInt {_field_var(d0.field, d0.key_arg)})), "
        f"[({_STORE_LOC}, LitDict {_nested_insert(info)})]; "
        f"split; [exists {_exists_args(info)}; repeat split; auto "
        f"| unfold updates_dom_in; constructor; [|constructor]; "
        f"simpl; rewrite Hcell; eexists; reflexivity]"
    )
    bullets = [f"  all: try solve [{success_script}]."]
    for i, (_n, _u1, _u2) in enumerate(arms):
        ex = info.exits[i]
        script = (
            f"injection Hfe as Heq; subst pre post; "
            f"destruct Hpre as "
            f"{_destruct_pat(info, ['Hvs', 'Hcell', 'Hlook', 'Hwhen'])}; "
            f"exists (RExn \"{ex.name}\" (LitTuple [{_exc_payload(info, ex)}])), []; "
            f"split; [exists {_exists_args(info)}; repeat split; auto "
            f"| unfold updates_dom_in; constructor]"
        )
        bullets.append(f"  all: try solve [{script}].")
    return f"""Lemma gen_table_total : forall f pre post vs sigma,
  gen_table f = Some (FunSpecS pre post) ->
  pre sigma vs ->
  exists r ups, post sigma vs r ups /\\ updates_dom_in sigma ups.
Proof.
  intros f pre post vs sigma Hfe Hpre. unfold gen_table in Hfe.
  destruct {eqbs};
    try discriminate.
{chr(10).join(bullets)}
Qed."""


def _totality_pure(info: ContractInfo, arms: list) -> str:
    eqbs = f'(String.eqb f "{info.name}")'
    for i in range(len(arms)):
        eqbs += f', (String.eqb f "{info.name}_exc{i}")'
    return f"""Lemma gen_table_total_pure : forall f pre post vs,
  gen_table f = Some (FunSpec pre post) ->
  pre vs -> exists v, post vs v.
Proof.
  intros f pre post vs Hfe _. unfold gen_table in Hfe.
  destruct {eqbs}; discriminate.
Qed."""


def _delta_hyp(info: ContractInfo, d: DeltaInfo) -> str:
    """The arithmetic hypothesis a delta's preservation proof needs:
    '-' always; '+' only when the delta hits the invariant's small field
    (the availability form)."""
    fv = _field_var(d.field, d.key_arg)
    if d.op == "-":
        return f"({fv} - {d.qty_arg} >= 0)%Z"
    if info.invariant_le and d.field == info.invariant_le[0]:
        big = _field_var(info.invariant_le[1], d.key_arg)
        return f"({big} - {fv} >= {d.qty_arg})%Z"
    return ""


def _preservation_lemma(info: ContractInfo, d: DeltaInfo, idx: int) -> str:
    key, qty, field, op = d.key_arg, d.qty_arg, d.field, d.op
    fields = " ".join(_field_var(f, key) for f in _row_fields(info))
    new_vals = _defaults(info, key)
    new_vals[field] = f"{_field_var(field, key)} {op} {qty}"
    new_row = _row_call2(info, new_vals)
    hyp = _delta_hyp(info, d)
    delta_hyp = f"\n  {hyp} ->" if hyp else ""
    delta_arg = " Hdelta" if hyp else ""
    n_clauses = len(info.non_neg) + (1 if info.invariant_le else 0)
    inv_tail = "[Hr Hlo]" if n_clauses > 1 else "Hr"
    inv_tac = "split; lia." if n_clauses > 1 else "lia."
    return f"""Lemma gen_preserves_inv_{idx} : forall {key} {qty} store_d {fields},
  dict_lookup_str {key} store_d = Some {_row_call2(info, _defaults(info, key))} ->
  row_inv {_row_call2(info, _defaults(info, key))} ->
  ({qty} > 0)%Z ->{delta_hyp}
  store_inv store_d ->
  store_inv (dict_insert_str {key} {new_row} store_d).
Proof.
  induction store_d as [|kv rest IH]; intros {fields} Hlook Hprod Hpos{delta_arg} Hinv;
    simpl in Hlook |- *.
  - discriminate.
  - destruct kv as [k0 v0].
    destruct Hinv as [Hfst Hrest].
    destruct k0 as [| | s | | | | | | | |]; simpl in *;
      try (split; [exact Hfst | apply (IH {fields} Hlook Hprod Hpos{delta_arg} Hrest)]).
    destruct (String.eqb {key} s) eqn:E.
    + apply String.eqb_eq in E. subst s.
      injection Hlook as Hlook. subst v0.
      split; [|exact Hrest].
      destruct Hprod as [{fields.replace(" ", "0 [")}0 [Heq {inv_tail}]
        {"]" * (len(info.row_fields) - 1)}].
      injection Heq as {" ".join(
          "He_" + _field_var(f, key) for f in _row_fields(info))}.
      subst {" ".join(
          _field_var(f, key) + "0" for f in _row_fields(info))}.
      exists {", ".join(
          [f"({_field_var(field, key)} {op} {qty})%Z"
           if f == field else _field_var(f, key)
           for f in _row_fields(info)])}.
      split; [reflexivity|]. {inv_tac}
    + split; [exact Hfst|].
      apply (IH {fields} Hlook Hprod Hpos{delta_arg} Hrest).
Qed."""


def _store_inv_lookup() -> str:
    return """Lemma store_inv_lookup : forall store_d k row,
  store_inv store_d ->
  dict_lookup_str k store_d = Some row ->
  row_inv row.
Proof.
  induction store_d as [|kv rest IH]; intros k row Hinv Hlook; simpl in *.
  - discriminate.
  - destruct kv as [k0 v0].
    destruct Hinv as [Hfst Hrest].
    destruct k0 as [| | s | | | | | | | |]; simpl in *;
      try (apply (IH k row Hrest Hlook)).
    destruct (String.eqb k s) eqn:E.
    + injection Hlook as Hlook. subst v0. exact Hfst.
    + apply (IH k row Hrest Hlook).
Qed."""


def _scalar_tac(lhs: str, op: str, rhs: str, info: ContractInfo) -> str:
    """The tactic for one requires scalar: arithmetic → lia, string
    equality → reflexivity, string disequality → congruence."""
    if op in ("<", "<=", ">", ">="):
        return "lia"
    if op == "=":
        return "reflexivity" if not _is_int_expr(rhs, info) else "lia"
    if op == "<>":
        return "congruence" if not _is_int_expr(rhs, info) else "lia"
    return "lia"


def _final_tactic(info: ContractInfo) -> str:
    """The closing tactic for O1's scalars ∧ avail remainder."""
    parts = []
    for lhs, op, rhs in info.scalars:
        parts.append(f"split; [{_scalar_tac(lhs, op, rhs, info)}|].")
    avail = avail_str(info)
    if avail is None:
        if parts:
            parts[-1] = parts[-1].replace("|].", " | exact I].")
            return "\n    ".join(parts)
        return "exact I"
    if info.exits and len(info.exits[0].when_clauses) > 1:
        avail_tac = ("split; [try (right; lia); try (left; lia) | "
                     "try reflexivity; try lia; try congruence]")
    else:
        avail_tac = "lia"
    if parts:
        parts[-1] = parts[-1].replace("|].", f"| {avail_tac}].")
        return "\n    ".join(parts)
    return avail_tac


def _witness_row(info: ContractInfo) -> str:
    vals = {}
    first_int = True
    for f, _typ in info.row_fields:
        if _typ == "int":
            vals[f] = "100" if first_int else "10"
            first_int = False
        else:
            vals[f] = '"USD"'
    return _row_call2(info, vals)


def _witness_lits(info: ContractInfo) -> str:
    vals = []
    first_int = True
    for _f, _typ in info.row_fields:
        if _typ == "int":
            vals.append("100" if first_int else "10")
            first_int = False
        else:
            vals.append('"USD"')
    return ", ".join(vals)


def _o1(info: ContractInfo) -> str:
    keys = _keys(info)
    row = _witness_row(info)
    lits = _witness_lits(info)
    entries = "; ".join(f'(LitString "{k.upper()}1", {row})' for k in keys)
    vs = "; ".join([*(f'LitString "{k.upper()}1"' for k in keys),
                    'LitString "O1"', "LitInt 5"])
    exists_vars = ", ".join([*(f'"{k.upper()}1"' for k in keys), '"O1"', "5%Z",
                             f"[{entries}]",
                             *(_witness_lits(info) for _ in keys)])
    lookups = "\n    ".join(
        ["split; [apply lookup_insert_eq|]."]
        + ["split; [reflexivity|]."] * (len(keys) - 1)
    )
    row_inv_script = f"exists {lits}. split; [reflexivity|]. repeat split; lia."
    return f"""
(** O1: admissibility sanity — some state and args satisfy pre ∧ invariant. *)
Lemma o1_admissibility_sanity :
  exists sigma vs, gen_pre sigma vs /\\ store_inv [{entries}].
Proof.
  exists {{[ {_STORE_LOC} := LitDict [{entries}];
             {_TRACE_LOC} := LitList [] ]}},
         [{vs}].
  split.
  - exists {exists_vars}.
    split; [reflexivity|].
    {lookups}
    split; [reflexivity|].
    {_final_tactic(info)}
  - repeat split; try exact I.
    {row_inv_script}
    {row_inv_script if len(keys) > 1 else ""}
Qed."""


def _o2(info: ContractInfo) -> str:
    return f"""
(** O2: spec consistency — totality gives a post-satisfying outcome. *)
Lemma o2_spec_consistency : forall sigma vs,
  gen_pre sigma vs ->
  exists r ups, gen_post sigma vs r ups /\\ updates_dom_in sigma ups.
Proof.
  intros sigma vs Hpre.
  eapply (gen_table_total "{info.name}" gen_pre gen_post vs sigma
            eq_refl Hpre).
Qed."""


def _o3s(info: ContractInfo, arms: list) -> str:
    out = []
    for i, (n, _u1, _u2) in enumerate(arms):
        ex = info.exits[i]
        out.append(f"""
(** O3.{i}: exception consistency — the {ex.name} arm is satisfiable. *)
Lemma o3_{i}_exception_consistency : forall sigma vs,
  {n}pre sigma vs ->
  exists r ups, {n}post sigma vs r ups /\\ updates_dom_in sigma ups.
Proof.
  intros sigma vs Hpre.
  destruct Hpre as {_destruct_pat(info, ['Hvs', 'Hcell', 'Hlook', 'Hwhen'])}.
  exists (RExn "{ex.name}" (LitTuple [{_exc_payload(info, ex)}])), [].
  split.
  - exists {_exists_args(info)}. repeat split; auto.
  - unfold updates_dom_in. constructor.
Qed.""")
    return "\n".join(out)


def _o4(info: ContractInfo) -> str:
    if not info.exits:
        return ""
    avail = avail_str(info)
    whens = " \\/ ".join(
        "(" + " /\\ ".join(
            _z(f"{lhs} {o} {r}", info) for lhs, o, r in ex.when_clauses)
        + ")"
        for ex in info.exits
    )
    int_vars = " ".join(
        _field_var(f, k) for k in _keys(info)
        for f, _t in info.row_fields if _t == "int"
    ) + " " + info.deltas[0].qty_arg
    str_vars = " ".join(
        _field_var(f, k) for k in _keys(info)
        for f, _t in info.row_fields if _t == "str"
    ) + " " + " ".join(_keys(info))
    has_str = any(
        not _is_int_expr(lhs, info) or not _is_int_expr(r, info)
        for ex in info.exits
        for lhs, o, r in ex.when_clauses
    )
    if has_str:
        # find the string comparison sides (currency-style) and the
        # arithmetic decider (qty vs its compared field)
        str_pairs = [
            (lhs, r) for ex in info.exits
            for lhs, o, r in ex.when_clauses
            if not _is_int_expr(lhs, info) and not _is_int_expr(r, info)
            and o in ("=", "<>")
        ]
        if str_pairs:
            s1, s2 = str_pairs[0]
            qty = info.deltas[0].qty_arg
            proof = f"""Proof.
  intros.
  destruct (String.eqb {s1} {s2}) eqn:E.
  - apply String.eqb_eq in E. subst {s2}.
    destruct (Z_ge_dec {_field_var(info.deltas[0].field, info.deltas[0].key_arg)} {qty})
      as [Hg | Hl].
    + left. split; [right; lia | reflexivity].
    + right. left. split; [reflexivity | lia].
  - right. right. apply String.eqb_neq. exact E.
Qed."""
        else:
            proof = "Proof. intros. intuition; try lia; try congruence. Qed."
    else:
        proof = "Proof. intros. lia. Qed."
    return f"""
(** O4: exit coverage — availability and the exit conditions partition. *)
Lemma o4_exit_coverage : forall ({int_vars} : Z) ({str_vars} : string),
  ({avail}) \\/ ({whens}).
{proof}"""


def _o5(info: ContractInfo) -> str:
    qty = info.deltas[0].qty_arg
    lookups_hyp = " ->\n    ".join(
        f"dict_lookup_str {k} store_d = Some {_row_call2(info, _defaults(info, k))}"
        for k in _keys(info)
    )
    str_binders = " ".join(_keys(info)) + " order"
    typed = []
    if str_binders.strip():
        typed.append(f"({str_binders} : string)")
    typed.append(f"({qty} : Z)")
    typed.append("(store_d : list (sn_val * sn_val))")
    int_fields_vars = " ".join(
        _field_var(f, k) for k in _keys(info)
        for f, _t in info.row_fields if _t == "int"
    )
    if int_fields_vars:
        typed.append(f"({int_fields_vars} : Z)")
    str_fields_vars = " ".join(
        _field_var(f, k) for k in _keys(info)
        for f, _t in info.row_fields if _t == "str"
    )
    if str_fields_vars:
        typed.append(f"({str_fields_vars} : string)")
    typed_binders = " ".join(typed)
    avail = avail_str(info)
    avail_hyp = f"\n  ({avail}) ->" if avail else ""
    avail_intro = " Havail" if avail else ""
    intro_vars = " ".join(
        [*_keys(info), "order", qty, "store_d"]
        + [
            _field_var(f, k) for k in _keys(info)
            for f, _t in info.row_fields if _t == "int"
        ]
        + [
            _field_var(f, k) for k in _keys(info)
            for f, _t in info.row_fields if _t == "str"
        ]
    )
    scalar_hyps = " ".join(
        f"Hsc{i}" for i in range(len(info.scalars))
    )
    scalar_intro = (
        f" [{scalar_hyps}]" if len(info.scalars) > 1 else f" {scalar_hyps}"
    ) if info.scalars else ""
    lookups_intro = " ".join(f"Hlook_{k}" for k in _keys(info))
    def _delta_brackets(d: DeltaInfo, first: bool, close_store: bool) -> str:
        parts = []
        if not first:
            parts.append(
                f"rewrite dict_lookup_insert_ne; "
                f"[exact Hlook_{d.key_arg} | congruence]"
            )
        else:
            parts.append(f"exact Hlook_{d.key_arg}")
        parts.append(
            f"eapply store_inv_lookup; [exact Hinv | exact Hlook_{d.key_arg}]"
        )
        parts.append("exact Hsc0" if info.scalars else "lia")
        if _delta_hyp(info, d):
            if (info.exits
                    and (len(info.exits) > 1
                         or len(info.exits[0].when_clauses) > 1)):
                parts.append(
                    "destruct Havail as [[Hc | Hok] Hav2]; [congruence | lia]"
                )
            else:
                parts.append("lia")
        if close_store:
            parts.append("exact Hinv")
        return "\n      | ".join(parts)

    n = len(info.deltas)
    if n == 1:
        proof = f"""Proof.
  intros {intro_vars}{scalar_intro}{avail_intro} {lookups_intro} Hinv.
  eapply gen_preserves_inv_0;
    [ {_delta_brackets(info.deltas[0], first=True, close_store=True)} ].
Qed."""
    else:
        first_d = info.deltas[0]
        outer_d = info.deltas[-1]
        inner = (
            "eapply gen_preserves_inv_0;\n        [ "
            + _delta_brackets(first_d, first=True, close_store=True)
            .replace("\n      | ", "\n        | ")
            + " ]"
        )
        proof = f"""Proof.
  intros {intro_vars}{scalar_intro}{avail_intro} {lookups_intro} Hinv.
  eapply gen_preserves_inv_{n - 1};
    [ {_delta_brackets(outer_d, first=False, close_store=False)}
      | {inner} ].
Qed."""
    return f"""
(** O5: invariant preservation across the nested delta updates. *)
Lemma o5_invariant_preservation : forall {typed_binders},
  ({_scalar_props(info)}) ->{avail_hyp}
  {lookups_hyp} ->
  store_inv store_d ->
  store_inv {_nested_insert(info)}.
{proof}"""


def _o8(info: ContractInfo) -> str:
    return f"""
(** O8: frame soundness — everything outside the declared frame is
    unchanged.  The generated footprint is the single store cell; every
    other location (including the trace cell) is preserved. *)
Lemma o8_frame_soundness : forall sigma vs r ups,
  gen_post sigma vs r ups ->
  forall l, l <> {_STORE_LOC} ->
    (apply_updates sigma ups) !! l = sigma !! l.
Proof.
  intros sigma vs r ups Hpost l Hne.
  destruct Hpost as {_destruct_pat(info, ['Hvs', 'Hcell', 'Hlook', 'Hr', 'Hups'])}.
  subst ups. simpl. apply lookup_insert_ne. congruence.
Qed."""


def _obligations(info: ContractInfo, arms: list) -> str:
    return "\n".join([
        _store_inv_lookup(),
        _o1(info),
        _o2(info),
        _o3s(info, arms),
        _o4(info),
        _o5(info),
        _o8(info),
    ])


def _witness_rows(info: ContractInfo) -> tuple[str, str]:
    """(insert form, lookup-check form) for O1's witness store."""
    row = _row_call2(
        info,
        {f: "100" if f == _row_fields(info)[0]
         else "10" if t == "int" else '"USD"'
         for f, t in info.row_fields},
    )
    return row, row


def emit_contract(info: ContractInfo, source: str) -> str:
    """Emit the full Coq obligation file for a contract."""
    arms = _exc(info)
    exc_texts = [t for _, pre, post in arms for t in (pre, post)]
    deferred = ""
    if info.log_writes:
        deferred = ("\n    Deferred (v2, trace emission): "
                    + ", ".join(info.log_writes))
    parts = [
        f"""(** GENERATED FILE — proof obligations for [{info.name}].

    Source contract: {source}
    Generator: specsaver.lower (v2).  Do not edit by hand.

    Shape: multi-delta over keyed rows, N exception arms, typed fields.{deferred} *)

From iris.proofmode Require Import proofmode.
From iris.base_logic.lib Require Import gen_heap.
Require Import SnakeletExnLang SnakeletExnWp.
Require Import SpecPrelude.

Section gen_{info.name}.
Context `{{FC : FunCtx}}.

Definition {_STORE_LOC} : loc := Loc 1%positive.
Definition {_TRACE_LOC} : loc := Loc 2%positive.
""",
        _row_ctor(info),
        _row_inv(info),
        _store_inv(),
        _pre(info),
        _post(info),
        *exc_texts,
        _table(info, arms),
        _totality_pure(info, arms),
        _totality(info, arms),
        *[_preservation_lemma(info, d, i) for i, d in enumerate(info.deltas)],
        "#[global] Instance gen_fun_ctx : FunCtx :=\n"
        "  {| fun_entries := gen_table;\n"
        "     fun_specs_total := gen_table_total_pure;\n"
        "     fun_specsS_total := gen_table_total |}.",
        _obligations(info, arms),
        f"End gen_{info.name}.",
    ]
    return "\n\n".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# Layered emission — one .v file per dependency layer for parallel proof
# ---------------------------------------------------------------------------


def _dependency_layers(info: ContractInfo) -> dict[int, list[tuple[str, str]]]:
    """Return layers of (lemma_name, lemma_content) tuples keyed by layer
    number.  Layer 0 has no lemma dependencies; higher layers depend on
    lower-numbered layers."""
    arms = _exc(info)
    layers: dict[int, list[tuple[str, str]]] = {}
    layers[0] = [
        ("o4_exit_coverage", _o4(info)),
        ("o1_admissibility_sanity", _o1(info)),
    ]
    layer1 = [("o2_spec_consistency", _o2(info))]
    layer1.extend(
        (f"o3_{i}_exception_consistency", o3)
        for i, o3 in enumerate(
            _o3s(info, arms).split("\n\n") if _o3s(info, arms) else []
        )
    )
    layers[1] = layer1
    l3 = [("store_inv_lookup", _store_inv_lookup())]
    for i, d in enumerate(info.deltas):
        l3.append((f"gen_preserves_inv_{i}", _preservation_lemma(info, d, i)))
    layers[2] = l3
    layers[3] = [
        ("o5_invariant_preservation", _o5(info)),
        ("o8_frame_soundness", _o8(info)),
    ]
    return layers


def _shared_defs(info: ContractInfo, source: str, arms: list) -> str:
    """Emit the shared definitions that all layer files import."""
    exc_texts = [t for _, pre, post in arms for t in (pre, post)]
    return "\n\n".join(p for p in [
        f"""(** SHARED DEFINITIONS — for [{info.name}].

    Source contract: {source}
    Generated by specsaver.lower (layered v3). *)

From iris.proofmode Require Import proofmode.
From iris.base_logic.lib Require Import gen_heap.
Require Import SnakeletExnLang SnakeletExnWp.
Require Import SpecPrelude.

Section gen_{info.name}.
Context `{{FC : FunCtx}}.

Definition {_STORE_LOC} : loc := Loc 1%positive.
Definition {_TRACE_LOC} : loc := Loc 2%positive.""",
        _row_ctor(info),
        _row_inv(info),
        _store_inv(),
        _pre(info),
        _post(info),
        *exc_texts,
        _table(info, arms),
        _store_inv_lookup(),
        _totality_pure(info, arms),
        _totality(info, arms),
        "#[global] Instance gen_fun_ctx : FunCtx :=\n"
        "  {| fun_entries := gen_table;\n"
        "     fun_specs_total := gen_table_total_pure;\n"
        "     fun_specsS_total := gen_table_total |}.",
        f"End gen_{info.name}.",
    ] if p)


def _statement_hash(text: str) -> str:
    """SHA-256 of the statement portion of a lemma (up to 'Proof.').

    Used by statements.json to enforce statement-immutability: if the
    prover rewrites the statement, the hash no longer matches and the
    outcome is UNPROVED (docs/proof-counterexample-workflow.md §4).
    """
    import hashlib
    stmt = text.split("Proof.")[0].strip()
    return hashlib.sha256(stmt.encode()).hexdigest()


def _row_literal(info: ContractInfo, fields: dict) -> str:
    """Build a row_of(...) call from a JSON field dict, ordered by the
    domain's row field declaration."""
    vals = " ".join(
        str(fields.get(f, 0)) for f in _row_fields(info)
    )
    return f"(row_of {vals})"


def _store_literal(info: ContractInfo, store: dict) -> str:
    """Build a list of (LitString key, row) pairs from a JSON store dict."""
    entries = "; ".join(
        f'(LitString "{k}", {_row_literal(info, v)})'
        for k, v in store.items()
    )
    return f"[{entries}]"


def _args_literal(info: ContractInfo, args: list) -> str:
    """Build the argument vector.  First arg is the key (string);
    remaining args are encoded positionally as LitString or LitInt."""
    lits = []
    for a in args:
        if isinstance(a, str):
            lits.append(f'LitString "{a}"')
        elif isinstance(a, bool):
            lits.append(f"LitBool {'true' if a else 'false'}")
        elif isinstance(a, (int, float)):
            lits.append(f"LitInt {int(a)}")
        else:
            lits.append(f'LitString "{a}"')
    return "[" + "; ".join(lits) + "]"


def _args_exists(info: ContractInfo, args: list) -> str:
    """Existential witnesses for the non-key args, in declaration order:
    strings quoted, ints with %Z.  args[0] is the key (handled separately)."""
    lits = []
    for a in args[1:]:
        if isinstance(a, str):
            lits.append(f'"{a}"')
        elif isinstance(a, bool):
            lits.append("true" if a else "false")
        else:
            lits.append(f"{int(a)}%Z")
    return ", ".join(lits)


def _row_exists(info: ContractInfo, store: dict, sku: str) -> str:
    """Existential witnesses for the looked-up row's fields, in the
    domain's row-field order, as %Z literals (or quoted strings)."""
    row = store.get(sku, {})
    lits = []
    for f, t in info.row_fields:
        v = row.get(f, 0)
        lits.append(f'"{v}"' if t == "str" else f"{v}%Z")
    return ", ".join(lits)


def _emit_lneg(info: ContractInfo, arms: list,
               witnesses: list[dict] | None) -> str:
    """Emit <name>_Lneg.v — the evidential negation layer.

    Contains the CounterWitness record, any candidate witnesses
    (materialized from runner JSON), computational satellite lemmas,
    and per-obligation bundling theorems.  See
    docs/proof-counterexample-workflow.md §5.
    """
    key = _keys(info)[0]

    out = [f"""(* Evidential negation layer for [{info.name}].

   Counter-examples as extractable data (CounterWitness), with
   computational satellite lemmas and per-obligation bundling
   theorems.  A DISPROVED verdict requires all satellites to close
   plus the bundling theorem — statement-immutability applies as in
   the positive layers. *)

From iris.proofmode Require Import proofmode.
From iris.base_logic.lib Require Import gen_heap.
Require Import SnakeletExnLang SnakeletExnWp.
Require Import SpecPrelude.
Require Import {info.name}_defs.

Section gen_{info.name}_Lneg.
Context `{{FC : FunCtx}}.

(* ── the witness as extractable data ── *)
Record CounterWitness := {{
  cw_store   : list (sn_val * sn_val);
  cw_key     : string;
  cw_args    : list sn_val;
  cw_bad_row : sn_val;
}}.

(* store_inv at a looked-up key gives row_inv — the L2 helper,
   proved inline so Lneg is self-contained. *)
Lemma store_inv_lookup : forall store_d k row,
  store_inv store_d ->
  dict_lookup_str k store_d = Some row ->
  row_inv row.
Proof.
  induction store_d as [|kv rest IH]; intros k row Hinv Hlook; simpl in *.
  - discriminate.
  - destruct kv as [k0 v0].
    destruct Hinv as [Hfst Hrest].
    destruct k0 as [| | s | | | | | | | |]; simpl in *;
      try (apply (IH k row Hrest Hlook)).
    destruct (String.eqb k s) eqn:E.
    + injection Hlook as Hlook. subst v0. exact Hfst.
    + apply (IH k row Hrest Hlook).
Qed.

(** Statement form for the invariant-preservation negation.

    A DISPROVED verdict on o5 (invariant preservation) takes this
    shape: a concrete key/delta whose updated store violates
    store_inv.  Candidates below instantiate it; the prover
    certifies or refutes each. *)
Theorem {info.name}_preservation_negation_form : forall (cw : CounterWitness),
  dict_lookup_str cw.(cw_key) cw.(cw_store) <> None ->
  ~ row_inv cw.(cw_bad_row) ->
  ~ store_inv (dict_insert_str cw.(cw_key) cw.(cw_bad_row) cw.(cw_store)).
Proof.
  intros cw Hlook Hbad Hcontra.
  apply Hbad.
  eapply store_inv_lookup.
  - exact Hcontra.
  - apply dict_lookup_insert_eq.
Qed.
"""]

    if witnesses:
        for i, w in enumerate(witnesses):
            store = w.get("store", {})
            args = w.get("args", [])
            computed = w.get("computed", {})
            sku = args[0] if args else key
            bad_row = _row_literal(info, computed)
            lookup_row = _row_literal(
                info, store.get(sku, computed) if sku in store else computed)
            sigma = (f'{{[store_loc := LitDict {_store_literal(info, store)};'
                     f'  trace_loc := LitList []]}}')
            out.append(f"""
(* ── candidate witness {i} ── *)
Definition cex_{i} : CounterWitness := {{|
  cw_store   := {_store_literal(info, store)};
  cw_key     := "{sku}";
  cw_args    := {_args_literal(info, args)};
  cw_bad_row := {bad_row};
|}}.

(** pre of the contract holds on the witness — decidable. *)
Lemma cex_{i}_pre_holds : gen_pre {sigma} cex_{i}.(cw_args).
Proof.
  unfold gen_pre.
  exists "{sku}", {_args_exists(info, args)},
    {_store_literal(info, store)}, {_row_exists(info, store, sku)}.
  split; [reflexivity|].
  split; [apply lookup_insert_eq|].
  split; [reflexivity|].
  split; [lia|].
  exact I.
Qed.

(** the update computes to the offending row — reflexivity. *)
Lemma cex_{i}_update_computes :
  dict_insert_str cex_{i}.(cw_key) cex_{i}.(cw_bad_row) cex_{i}.(cw_store)
  = {_store_literal(info, {sku: computed})}.
Proof. vm_compute. reflexivity. Qed.

(** the offending row violates the invariant — inversion + lia. *)
Lemma cex_{i}_violates_inv : ~ row_inv cex_{i}.(cw_bad_row).
Proof.
  intros [oh [rs [rp [Heq [Hge1 [Hge2 Hle]]]]]].
  injection Heq; intros; subst. lia.
Qed.

(** DISPROVED bundling theorem for candidate {i}. *)
Theorem cex_{i}_preservation_false :
  exists store_d k,
    dict_lookup_str k store_d
      = Some {lookup_row} /\\
    ~ store_inv (dict_insert_str k cex_{i}.(cw_bad_row) store_d).
Proof.
  exists cex_{i}.(cw_store), cex_{i}.(cw_key).
  split; [vm_compute; reflexivity |].
  eapply {info.name}_preservation_negation_form.
  - vm_compute. discriminate.
  - exact cex_{i}_violates_inv.
Qed.
""")

    out.append(f"""
End gen_{info.name}_Lneg.""")

    return "\n".join(out)


def emit_layered(info: ContractInfo, source: str, out_dir: str,
                 counter_witnesses: list[dict] | None = None) -> None:
    """Emit multiple .v files — one per dependency layer — plus
    a _CoqProject and schedule.json for parallel proof execution.

    counter_witnesses: optional list of candidate counter-examples
    (from the scenario runner or authored), each shaped:

        {"obligation": "invariant_preservation",
         "store": {"SKU1": {"on_hand": 10, "reserved": 8,
                            "reorder_point": 5}},
         "args": ["SKU1", "ORDER1", 5],
         "computed": {"on_hand": 10, "reserved": 13, "reorder_point": 5}}

    They are materialized into <name>_Lneg.v as CounterWitness
    definitions with computational satellite lemmas (see
    docs/proof-counterexample-workflow.md).
    """
    import json
    from pathlib import Path

    arms = _exc(info)
    layers = _dependency_layers(info)
    base = Path(out_dir)

    # Emit shared definitions
    base.mkdir(parents=True, exist_ok=True)
    defs_path = base / f"{info.name}_defs.v"
    defs_path.write_text(_shared_defs(info, source, arms))

    # Emit one file per layer, each importing prior layers
    layer_files = {}
    for layer_num in sorted(layers):
        lemmas = layers[layer_num]
        imports = [f"Require Import {info.name}_defs."]
        for prev in range(layer_num):
            imports.append(f"Require Import {info.name}_L{prev}.")
        content = f"""(* Layer {layer_num} obligations for [{info.name}]. *)
""" + ({
  0: """(** HINT: for the lookup subgoal, write EXACTLY:
      rewrite lookup_insert. rewrite decide_True. reflexivity. reflexivity.
    Do NOT use //, auto, nor destruct decide — they produce opaque proof terms
    that Qed rejects in coqc.
    For dict_lookup_str subgoal, write EXACTLY: simpl. reflexivity. *)

""",
  1: f"""(** HINT: for O2, use the pre-proved lemma:
      intros sigma vs Hpre.
      eapply (gen_table_total "{info.name}" gen_pre gen_post vs sigma eq_refl Hpre).
    For O3, destruct Hpre then: unfold updates_dom_in. constructor. *)

""",
}.get(layer_num, "")) + f"""
From iris.proofmode Require Import proofmode.
From iris.base_logic.lib Require Import gen_heap.
Require Import SnakeletExnLang SnakeletExnWp.
Require Import SpecPrelude.
{chr(10).join(imports)}

Section gen_{info.name}_L{layer_num}.
Context `{{FC : FunCtx}}.

""" + "\n\n".join(text for _, text in lemmas) + f"""

End gen_{info.name}_L{layer_num}."""
        fname = f"{info.name}_L{layer_num}.v"
        (base / fname).write_text(content)
        layer_files[str(layer_num)] = fname

    # Emit _CoqProject
    project_lines = [
        f"{info.name}_defs.v",
    ] + [layer_files[str(layer)] for layer in sorted(layer_files)]
    (base / "_CoqProject").write_text("\n".join(project_lines) + "\n")

    # Emit _skill.md — SnakeletExn proof patterns for rocq-piler.
    # Canonical source: skill_snakelet_exn.md (shipped with the package).
    _skill_src = Path(__file__).parent / "skill_snakelet_exn.md"
    (base / "_skill.md").write_text(_skill_src.read_text())

    # Emit <name>_Lneg.v — evidential negation layer (candidate
    # counter-examples + bundling theorems).
    lneg_fname = f"{info.name}_Lneg.v"
    (base / lneg_fname).write_text(_emit_lneg(info, arms, counter_witnesses))
    project_lines.append(lneg_fname)
    (base / "_CoqProject").write_text("\n".join(project_lines) + "\n")

    # Emit statements.json — hash of every obligation statement, for
    # the statement-immutability check (workflow doc §4.1).
    obligations = []
    for layer_num in sorted(layers):
        for name, text in layers[layer_num]:
            obligations.append({
                "name": name,
                "layer": layer_num,
                "file": layer_files[str(layer_num)],
                "statement_hash": _statement_hash(text),
            })
    (base / "statements.json").write_text(json.dumps({
        "contract": info.name,
        "obligations": obligations,
    }, indent=2) + "\n")

    # Emit bench_spec.json — compile deps, prove phases, suite tagging.
    suite = source.split(":")[0].split(".")[1] if ":" in source else source
    sorted_layers = sorted(layers.keys())
    bench_spec = {
        "contract": info.name,
        "suite": suite,
        "tags": ["heap", "stateful", "Iris"],
        "compile": {
            "shared": ["SnakeletExnLang.v", "SnakeletExnWp.v", "SpecPrelude.v"],
            "per_contract": [f"{info.name}_defs.v"],
        },
        "prove": {
            "phases": [
                {
                    "files": [layer_files[str(layer)]],
                    "maxParallel": 1,
                }
                for layer in sorted_layers
            ],
        },
    }
    (base / "bench_spec.json").write_text(json.dumps(bench_spec, indent=2) + "\n")

    # Emit schedule.json — parallel execution DAG.
    # Phases: positive layers [L0+L2, L1+L3] plus Lneg (independent —
    # certifies candidate witnesses in parallel with the positives).
    n_layers = len(sorted_layers)
    phases = []
    if n_layers >= 2:
        phase1 = [f"{info.name}_L{i}.v" for i in (0, 2) if i in layers]
        phase2 = [f"{info.name}_L{i}.v" for i in (1, 3) if i in layers]
        phases = [
            {"files": phase1, "maxParallel": len(phase1)},
            {"files": phase2, "maxParallel": len(phase2)},
        ]
    phases.append({"files": [lneg_fname], "maxParallel": 1})
    (base / "schedule.json").write_text(json.dumps({
        "contract": info.name,
        "phases": phases,
    }, indent=2) + "\n")
