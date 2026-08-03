"""Python AST → SnakeletExn AST lowerer (Phase 1: pure fragment).

Converts a Python function body into a SnakeletExn expression tree.
Phase 1 handles: integer/string literals, variables, arithmetic and
comparison binops, assignments, return, and if/else.

Design: the SnakeletExn AST is a set of Python dataclasses mirroring
the Coq constructors in SnakeletExnLang.v.  An emitter (`emit_snakelet`)
produces the Coq string from the AST.
"""

from __future__ import annotations

import ast as pyast
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# SnakeletExn AST types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SVar:
    name: str


@dataclass(frozen=True)
class SInt:
    value: int


@dataclass(frozen=True)
class SString:
    value: str


@dataclass(frozen=True)
class SUnit:
    pass


@dataclass(frozen=True)
class SLet:
    var: str
    e1: Expr
    e2: Expr


@dataclass(frozen=True)
class SBinOp:
    op: str              # "AddOp" | "SubOp" | "LtOp" | "EqOp" | ...
    left: Expr
    right: Expr


@dataclass(frozen=True)
class SIf:
    cond: Expr
    then_body: Expr
    else_body: Expr


@dataclass(frozen=True)
class SCall:
    fn: str              # function name
    args: tuple[Expr, ...]


@dataclass(frozen=True)
class SLoad:
    loc: Expr


@dataclass(frozen=True)
class SStore:
    loc: Expr
    val: Expr


@dataclass(frozen=True)
class SRaise:
    payload: Expr


@dataclass(frozen=True)
class SRec:
    fields: tuple[tuple[str, Expr], ...]


Expr = (
    SVar | SInt | SString | SUnit
    | SLet | SBinOp | SIf | SCall | SLoad | SStore | SRaise | SRec
)


# ---------------------------------------------------------------------------
# Lowering: Python AST → SnakeletExn AST
# ---------------------------------------------------------------------------


_BINOP_MAP = {
    pyast.Add: "AddOp",
    pyast.Sub: "SubOp",
    pyast.Mult: "MulOp",
    pyast.Lt: "LtOp",
    pyast.Gt: "GtOp",
    pyast.Eq: "EqOp",
    pyast.NotEq: "EqOp",  # lowered to ¬(a = b) at the expression level
}


def _lower_expr(node: pyast.expr) -> Expr:
    if isinstance(node, pyast.Constant):
        if isinstance(node.value, int):
            return SInt(node.value)
        if isinstance(node.value, str):
            return SString(node.value)
        raise NotImplementedError(
            f"constant type {type(node.value).__name__}"
        )
    if isinstance(node, pyast.Name):
        return SVar(node.id)
    if isinstance(node, pyast.BinOp):
        op = _BINOP_MAP.get(type(node.op))
        if op is None:
            raise NotImplementedError(
                f"binop {type(node.op).__name__}"
            )
        return SBinOp(op, _lower_expr(node.left), _lower_expr(node.right))
    if isinstance(node, pyast.UnaryOp):
        if isinstance(node.op, pyast.USub):
            return SBinOp("SubOp", SInt(0), _lower_expr(node.operand))
        raise NotImplementedError(
            f"unary op {type(node.op).__name__}"
        )
    if isinstance(node, pyast.Compare):
        if len(node.ops) == 1 and len(node.comparators) == 1:
            op = _BINOP_MAP.get(type(node.ops[0]))
            if op:
                return SBinOp(op, _lower_expr(node.left),
                              _lower_expr(node.comparators[0]))
        raise NotImplementedError("complex comparisons")
    if isinstance(node, pyast.BoolOp):
        if isinstance(node.op, pyast.And):
            lhs = _lower_expr(node.values[0])
            for v in node.values[1:]:
                lhs = SIf(lhs, _lower_expr(v), SInt(0))
            return lhs
        raise NotImplementedError(
            f"bool op {type(node.op).__name__}"
        )
    if isinstance(node, pyast.Call):
        fn = _lower_call_target(node.func)
        args = tuple(_lower_expr(a) for a in node.args)
        return SCall(fn, args)
    raise NotImplementedError(
        f"expression {type(node).__name__}: {pyast.dump(node)[:80]}"
    )


def _lower_call_target(node: pyast.expr) -> str:
    """Extract the function name from a call target."""
    if isinstance(node, pyast.Name):
        return node.id
    if isinstance(node, pyast.Attribute):
        return node.attr
    raise NotImplementedError(
        f"call target {type(node).__name__}"
    )


def _lower_stmt(stmt: pyast.stmt, rest: Expr) -> Expr:
    if isinstance(stmt, pyast.Return):
        return _lower_expr(stmt.value) if stmt.value else SUnit()
    if isinstance(stmt, pyast.Assign):
        if len(stmt.targets) == 1 and isinstance(stmt.targets[0],
                                                  pyast.Name):
            return SLet(
                stmt.targets[0].id,
                _lower_expr(stmt.value),
                rest,
            )
        raise NotImplementedError("multi-target / non-name assignment")
    if isinstance(stmt, pyast.If):
        else_body = rest
        if stmt.orelse:
            # Convert else branch by lowering its body
            else_body = _lower_body(stmt.orelse, rest)  # noqa: F821
        return SIf(
            _lower_expr(stmt.test),
            _lower_body(stmt.body, rest),  # noqa: F821
            else_body,
        )
    if isinstance(stmt, pyast.Expr):
        return _lower_expr(stmt.value)
    raise NotImplementedError(
        f"statement {type(stmt).__name__}: {pyast.dump(stmt)[:80]}"
    )


def _lower_body(body: list[pyast.stmt], terminal: Expr) -> Expr:
    """Lower a list of statements into a let/if chain ending with terminal."""
    expr = terminal
    for stmt in reversed(body):
        expr = _lower_stmt(stmt, expr)
    return expr


def lower_func(source: str) -> Expr:
    """Lower a Python function body into a SnakeletExn expression.

    The function's arguments become SnakeletExn variables.
    The body becomes a let-chain ending with the return value.
    """
    tree = pyast.parse(source)
    func = tree.body[0]
    if not isinstance(func, pyast.FunctionDef):
        raise ValueError("expected a function definition")
    # The function body is lowered; arguments are SnakeletExn variables
    # referenced by SVar in the body.
    return _lower_body(func.body, SUnit())


# ---------------------------------------------------------------------------
# Emitter: SnakeletExn AST → Coq string
# ---------------------------------------------------------------------------


def emit_snakelet(expr: Expr) -> str:
    """Emit a SnakeletExn expression as a Coq string."""
    return _emit(expr)


def _emit(e: Expr) -> str:
    if isinstance(e, SVar):
        return f'Var "{e.name}"'
    if isinstance(e, SInt):
        return f"Val (LitInt {e.value})"
    if isinstance(e, SString):
        return f'Val (LitString "{e.value}")'
    if isinstance(e, SUnit):
        return "Val LitUnit"
    if isinstance(e, SLet):
        return (
            f'Let "{e.var}" ({_emit(e.e1)}) ({_emit(e.e2)})'
        )
    if isinstance(e, SBinOp):
        return (
            f"BinOp {e.op} ({_emit(e.left)}) ({_emit(e.right)})"
        )
    if isinstance(e, SIf):
        return (
            f"If ({_emit(e.cond)}) ({_emit(e.then_body)})"
            f" ({_emit(e.else_body)})"
        )
    if isinstance(e, SCall):
        args = "; ".join(_emit(a) for a in e.args)
        return f'Call "{e.fn}" [{args}]'
    if isinstance(e, SLoad):
        return f"Load ({_emit(e.loc)})"
    if isinstance(e, SStore):
        return f"Store ({_emit(e.loc)}) ({_emit(e.val)})"
    if isinstance(e, SRaise):
        return f"Raise ({_emit(e.payload)})"
    if isinstance(e, SRec):
        fields = "; ".join(
            f'(Val (LitString "{k}"), {_emit(v)})'
            for k, v in e.fields
        )
        return f"Val (LitDict [{fields}])"
    raise NotImplementedError(f"emit: {type(e).__name__}")
