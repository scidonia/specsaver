"""Introspect a Contract into the shapes the emitter needs (v2).

v2 shape: multi-delta (several keyed updates, possibly different keys),
multiple exception arms, conjunctive `when` conditions, and typed row
fields (int and string).  Conservative: anything outside raises
UnsupportedShapeError loudly.
"""

from __future__ import annotations

import ast
import dataclasses
from dataclasses import dataclass

from specsaver.contract_model import Contract, ExcExit
from specsaver.render import _extract_return_expression_with_params


class UnsupportedShapeError(Exception):
    pass


def _lint_pure(pred, where: str) -> None:
    """Gate every clause through the purity validator before emission."""
    from specsaver.purity import PurityError, check_purity

    try:
        check_purity(pred)
    except PurityError as exc:
        raise UnsupportedShapeError(
            f"impure predicate in {where}: {exc}"
        ) from exc


@dataclass(frozen=True)
class DeltaInfo:
    key_arg: str     # args field used as the map key for this delta
    field: str       # row field changed
    op: str          # "+" | "-"
    qty_arg: str     # args field operand


@dataclass(frozen=True)
class ExitInfo:
    name: str            # exception class name
    code: str            # its .code
    payload: tuple[str, ...]   # exc field names read by ensures
    when_clauses: tuple[tuple[str, str, str], ...]  # (lhs, op, rhs) conjuncts


@dataclass(frozen=True)
class TraceFieldInfo:
    name: str      # e.g. "sku"
    kind: str      # "args" | "result" | "exc" | "var" | "expr"
    expr: str      # the variable / expression — e.g. "sku", "reservation_id"
    field_type: str  # "int" | "str"


@dataclass(frozen=True)
class TraceInfo:
    """One ``extends_by_one`` trace obligation."""
    log_field: str       # e.g. "reservation_log"
    event_fields: tuple[TraceFieldInfo, ...]


def _field_type_for(name: str, info_fields: tuple[tuple[str, str], ...],
                    qty_arg: str) -> str:
    """Determine if an args field is int or str."""
    for f, t in info_fields:
        if f == name:
            return t
    if name == qty_arg:
        return "int"
    # Default: look at the arg names — quantity-like fields are int
    if name in ("quantity", "amount", "now", "created_at", "expires_at"):
        return "int"
    return "str"


@dataclass(frozen=True)
class ContractInfo:
    name: str            # operation name ("reserve")
    row_fields: tuple[tuple[str, str], ...]  # (name, "int"|"str"), sans key field
    map_field: str       # observed map field ("products")
    deltas: tuple[DeltaInfo, ...]
    scalars: tuple[tuple[str, str, str], ...]  # (lhs, op, rhs) requires
    invariant_le: tuple[str, str] | None  # (small, big) e.g. reserved/on_hand
    non_neg: tuple[str, ...]              # fields constrained >= 0 (e.g. balance)
    exits: tuple[ExitInfo, ...]
    log_writes: tuple[str, ...]    # trace write paths deferred to trace emission (v2)
    traces: tuple[TraceInfo, ...]   # extends_by_one obligations for trace cells
    avail: str | None  # success availability as a Coq Prop string; None if no exits


_NEGATE = {"<": ">=", "<=": ">", ">": "<=", ">=": "<", "=": "<>", "<>": "="}
_OP_MAP = {ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=",
           ast.Eq: "=", ast.NotEq: "<>"}


def _body(pred) -> ast.expr:
    """Parse a predicate's extracted body expression."""
    src, _ = _extract_return_expression_with_params(pred)
    if src is None:
        raise UnsupportedShapeError(f"no source for {pred!r}")
    return ast.parse(src, mode="eval").body


def _validate_frame(contract: Contract, map_field: str,
                    deltas: tuple[DeltaInfo, ...]) -> tuple[str, ...]:
    """Every map write must be one of the deltas; logs deferred to v2."""
    from specsaver.frames import parse_write_path

    expected = {(map_field, d.key_arg, d.field) for d in deltas}
    log_writes: list[str] = []
    for w in contract.writes:
        try:
            path = parse_write_path(w)
        except ValueError as exc:
            raise UnsupportedShapeError(str(exc)) from exc
        if path.attr is None:
            log_writes.append(w)
        elif path.key is None:
            raise UnsupportedShapeError(f"map write path needs a key: {w!r}")
        elif (path.field, path.key, path.attr) not in expected:
            raise UnsupportedShapeError(
                f"write state.{path.field}[{path.key}].{path.attr} is not a "
                f"delta of this contract — the spec would write outside its "
                f"declared frame"
            )
    return tuple(log_writes)


def _find_deltas(contract: Contract) -> tuple[DeltaInfo, ...]:
    """Collect delta clauses: new.<map>[key].<f> == old ± args.<a>."""
    matches: list[DeltaInfo] = []
    for pred in contract.ensures:
        src, _ = _extract_return_expression_with_params(pred)
        if src is None or "==" not in src:
            continue
        try:
            body = _body(pred)
        except UnsupportedShapeError:
            continue
        if not (isinstance(body, ast.Compare) and len(body.ops) == 1
                and isinstance(body.ops[0], ast.Eq)):
            continue
        left, right = body.left, body.comparators[0]
        if not (isinstance(left, ast.Attribute)
                and isinstance(left.value, ast.Subscript)):
            continue
        field_name = left.attr
        if not isinstance(right, ast.BinOp):
            continue
        if not isinstance(right.op, (ast.Add, ast.Sub)):
            continue
        # key: the args attribute used as the map subscript on the left
        key_arg = None
        sub = left.value
        if (isinstance(sub.slice, ast.Attribute)
                and isinstance(sub.slice.value, ast.Name)
                and sub.slice.value.id == "args"):
            key_arg = sub.slice.attr
        qty_arg = None
        for operand in (right.left, right.right):
            if (isinstance(operand, ast.Attribute)
                    and isinstance(operand.value, ast.Name)
                    and operand.value.id == "args"):
                qty_arg = operand.attr
        if key_arg is None or qty_arg is None:
            continue
        op = "+" if isinstance(right.op, ast.Add) else "-"
        d = DeltaInfo(key_arg=key_arg, field=field_name, op=op, qty_arg=qty_arg)
        if d not in matches:
            matches.append(d)
    if not matches:
        raise UnsupportedShapeError("no delta clause found in ensures")
    qty_args = {d.qty_arg for d in matches}
    if len(qty_args) > 1:
        raise UnsupportedShapeError(
            f"deltas use different quantity args: {sorted(qty_args)}"
        )
    return tuple(matches)


def _find_traces(contract: Contract, row_fields, qty_arg) -> tuple[TraceInfo, ...]:
    """Find ``extends_by_one`` trace obligations in ensures (success path
    only; exception-arm traces deferred to a later lowering pass)."""
    results: list[TraceInfo] = []
    for pred in contract.ensures:
        try:
            body = _body(pred)
        except UnsupportedShapeError:
            continue
        _collect_trace(body, results, row_fields, qty_arg)
    return tuple(
        t for t in results
        if t.event_fields and all(
            f.kind in ("args", "var") for f in t.event_fields
        )
    )


def _collect_trace(
    body: ast.expr, results: list[TraceInfo],
    row_fields, qty_arg,
) -> None:
    """Extract extends_by_one(old.observed.<X>, new.observed.<X>, λe: ...)."""
    if not isinstance(body, ast.Call):
        return
    func = body.func
    if (isinstance(func, ast.Name) and func.id == "extends_by_one"
            and len(body.args) == 3):
        args = body.args
        # Extract log field from old.observed.<field> pattern
        log = _extract_observed_field(args[0])
        if log is None:
            return
        # Extract event fields from the lambda
        pred_body = args[2]
        if isinstance(pred_body, ast.Lambda):
            raw_fields = _extract_event_fields(pred_body.body)
            fields = _make_trace_fields(raw_fields, row_fields, qty_arg)
            results.append(TraceInfo(
                log_field=log,
                event_fields=tuple(fields),
            ))
    if isinstance(body, ast.BoolOp) and isinstance(body.op, ast.And):
        for v in body.values:
            _collect_trace(v, results, row_fields, qty_arg)


def _extract_observed_field(node: ast.expr) -> str | None:
    """Extract the log field name from: old_s.observed.<field>."""
    if not isinstance(node, ast.Attribute):
        return None
    sub = node.value
    if not isinstance(sub, ast.Attribute):
        return None
    if not isinstance(sub.value, ast.Name):
        return None
    if sub.attr == "observed":
        return node.attr
    return None


def _extract_event_fields(
    body: ast.expr,
) -> list[tuple[str, str, str]]:
    """Extract (field_name, kind, value_expr) from lambda body."""
    fields: list[tuple[str, str, str]] = []
    children = body.values if (
        isinstance(body, ast.BoolOp) and isinstance(body.op, ast.And)
    ) else [body]
    for child in children:
        if not (isinstance(child, ast.Compare)
                and len(child.ops) == 1
                and isinstance(child.ops[0], ast.Eq)):
            continue
        left = child.left
        right = child.comparators[0]
        if not isinstance(left, ast.Attribute):
            continue
        if (isinstance(left.value, ast.Name)
                and left.value.id in ("e", "g", "a", "f")):
            field_name = left.attr
            kind, expr = _source_kind(right)
            fields.append((field_name, kind, expr))
    return fields


def _make_trace_fields(
    raw: list[tuple[str, str, str]],
    row_fields: tuple[tuple[str, str], ...],
    qty_arg: str,
) -> list[TraceFieldInfo]:
    return [
        TraceFieldInfo(
            name=name, kind=kind, expr=expr,
            field_type=_field_type_for(name, row_fields, qty_arg),
        )
        for name, kind, expr in raw
    ]


def _source_kind(node: ast.expr) -> tuple[str, str]:
    """Determine where an event field value comes from."""
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        if node.value.id == "args":
            return "args", node.attr
        if node.value.id == "result":
            return "result", node.attr
        if node.value.id in ("exc",):
            return "exc", node.attr
    if isinstance(node, ast.Name):
        return "var", node.id
    return "expr", ast.unparse(node)


def _parse_comparison(body: ast.expr, map_field: str) -> tuple[str, str, str]:
    """Parse one comparison into (lhs, op, rhs) — lhs/rhs as Coq-side
    strings over per-key row variables or args."""
    if not isinstance(body, ast.Compare) or len(body.ops) != 1:
        raise UnsupportedShapeError(
            f"not a comparison: {ast.unparse(body)}"
        )
    op = _OP_MAP.get(type(body.ops[0]))
    if op is None:
        raise UnsupportedShapeError(f"unsupported op: {ast.unparse(body)}")
    lhs = _side_to_str(body.left, map_field)
    rhs = _side_to_str(body.comparators[0], map_field)
    return lhs, op, rhs


def _side_to_str(node: ast.expr, map_field: str) -> str:
    """A comparison side: args.<f> → the arg name; row field access
    state.observed.<map>[args.<k>].<f> → '<f>_<k>' (per-key variable);
    arithmetic over those → recurse."""
    if isinstance(node, ast.Attribute):
        if isinstance(node.value, ast.Name) and node.value.id == "args":
            return node.attr
        if isinstance(node.value, ast.Subscript):
            sub = node.value
            if isinstance(sub.slice, ast.Attribute):
                return f"{node.attr}_{sub.slice.attr}"
        raise UnsupportedShapeError(f"unsupported side: {ast.unparse(node)}")
    if isinstance(node, ast.Constant):
        return repr(node.value) if isinstance(node.value, str) else str(node.value)
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub)):
        op = "+" if isinstance(node.op, ast.Add) else "-"
        return (f"{_side_to_str(node.left, map_field)} {op} "
                f"{_side_to_str(node.right, map_field)}")
    raise UnsupportedShapeError(f"unsupported side: {ast.unparse(node)}")


def _split_and(node: ast.expr) -> list[ast.expr]:
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And):
        return [p for v in node.values for p in _split_and(v)]
    return [node]


def _parse_when_clauses(
    exit_: ExcExit, map_field: str,
) -> tuple[tuple[str, str, str], ...]:
    """Parse an exit's `when` list into a conjunction of comparisons."""
    clauses = []
    for pred in exit_.when:
        for part in _split_and(_body(pred)):
            clauses.append(_parse_comparison(part, map_field))
    if not clauses:
        raise UnsupportedShapeError(f"exit {exit_.raises.__name__}: empty when")
    return tuple(clauses)


def _introspect_exit(exit_: ExcExit, map_field: str) -> ExitInfo:
    name = exit_.raises.__name__
    code = getattr(exit_.raises, "code", name)
    payload: list[str] = []
    for pred in exit_.ensures:
        src, _ = _extract_return_expression_with_params(pred)
        if src is None:
            continue
        for node in ast.walk(ast.parse(src, mode="eval")):
            if (isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Name)
                    and node.value.id == "exc"
                    and node.attr not in payload):
                payload.append(node.attr)
    return ExitInfo(name=name, code=code, payload=tuple(payload),
                    when_clauses=_parse_when_clauses(exit_, map_field))


def _negate_clause(lhs: str, op: str, rhs: str) -> str:
    return f"({lhs} {_NEGATE[op]} {rhs})"


def _build_avail(exits: tuple[ExitInfo, ...]) -> str | None:
    """Success availability = ¬(∃i. when_i) = ∧i ∨j ¬c_ij, as a Coq Prop."""
    if not exits:
        return None
    arms = []
    for ex in exits:
        negs = " \\/ ".join(_negate_clause(lhs, o, r) for lhs, o, r in ex.when_clauses)
        arms.append(f"({negs})")
    return " /\\ ".join(arms)


def _scalar_requires(pred, map_field: str) -> tuple[str, str, str]:
    return _parse_comparison(_body(pred), map_field)


def introspect_contract(
    contract: Contract,
    row_type: type,
    map_field: str,
    key_arg: str,
) -> ContractInfo:
    """Extract the emission-relevant shape from a contract (v2)."""
    if not dataclasses.is_dataclass(row_type):
        raise UnsupportedShapeError(f"row type {row_type} is not a dataclass")

    def _type_name(tp) -> str:
        return tp if isinstance(tp, str) else getattr(tp, "__name__", "")

    row_fields = tuple(
        (f.name, t) for f in dataclasses.fields(row_type)
        if f.name not in ("id", key_arg)
        for t in [_type_name(f.type)]
        if t in ("int", "str")
    )
    if not row_fields:
        raise UnsupportedShapeError(f"row type {row_type} has no int/str fields")

    deltas = _find_deltas(contract)

    clauses = (
        [("requires", p) for p in contract.requires]
        + [("ensures", p) for p in contract.ensures]
        + [("invariant", p) for p in contract.invariants]
        + [
            (f"exception[{e.raises.__name__}]", p)
            for e in contract.exceptions
            for p in (*e.when, *e.ensures)
        ]
    )
    for where, pred in clauses:
        _lint_pure(pred, where)

    scalars = []
    for pred in contract.requires:
        try:
            scalars.append(_scalar_requires(pred, map_field))
        except UnsupportedShapeError:
            continue  # membership requires — structural
    scalars = tuple(scalars)

    invariant_le = None
    non_neg: list[str] = []
    for pred in contract.invariants:
        src, _ = _extract_return_expression_with_params(pred)
        if not src:
            continue
        tree = ast.parse(src, mode="eval")
        for node in ast.walk(tree):
            if (isinstance(node, ast.Compare) and len(node.ops) == 1):
                if isinstance(node.ops[0], ast.LtE) and \
                        isinstance(node.left, ast.Attribute) and \
                        isinstance(node.comparators[0], ast.Attribute):
                    invariant_le = (node.left.attr, node.comparators[0].attr)
                if isinstance(node.ops[0], ast.GtE) and \
                        isinstance(node.left, ast.Attribute) and \
                        isinstance(node.comparators[0], ast.Constant) and \
                        node.comparators[0].value == 0:
                    non_neg.append(node.left.attr)

    exits = tuple(_introspect_exit(e, map_field) for e in contract.exceptions)
    avail = _build_avail(exits)
    log_writes = _validate_frame(contract, map_field, deltas)
    traces = _find_traces(contract, row_fields, deltas[0].qty_arg if deltas else "")

    name = getattr(contract.impl, "__name__", "op")
    return ContractInfo(
        name=name,
        row_fields=row_fields,
        map_field=map_field,
        deltas=deltas,
        scalars=scalars,
        invariant_le=invariant_le,
        non_neg=tuple(dict.fromkeys(non_neg)),
        exits=exits,
        log_writes=log_writes,
        traces=traces,
        avail=avail,
    )
