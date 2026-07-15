"""Contract rendering — display registered contracts as readable conjunctions.

Two renderers are provided:
  - `render_precondition(entry_point)` — Python-like text
  - `render_precondition(entry_point, mode='math')` — compact mathematical notation
  - `render_contract(entry_point)` — pre, post, and invariant blocks

Every precondition/postcondition registered for an entry_point is conjoined
into a single formula, giving the "at-a-glance" view of the full contract.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from collections.abc import Callable

from specsaver.registry import ContractRecord, get_registry

_CONJUNCTION_PYTHON = " and "
_CONJUNCTION_MATH = " ∧ "
_INDENT = "      "


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def render_precondition(entry_point: str, mode: str = "python") -> str:
    """All preconditions for an entry point, conjoined."""
    records = get_registry().preconditions_for(entry_point)
    if not records:
        return "True"
    return _render_conjunction(records, mode)


def render_postcondition(entry_point: str, mode: str = "python") -> str:
    """All postconditions for an entry point, conjoined."""
    records = get_registry().postconditions_for(entry_point)
    if not records:
        return "True"
    return _render_conjunction(records, mode)


def render_invariant(entry_point: str, mode: str = "python") -> str:
    """All invariants for an entry point, conjoined."""
    records = get_registry().invariants_for(entry_point)
    if not records:
        return "True"
    return _render_conjunction(records, mode)


def render_contract(entry_point: str) -> str:
    """Full display: pre, post, and invariant blocks in math notation."""
    pre = render_precondition(entry_point, mode="math")
    post = render_postcondition(entry_point, mode="math")
    inv = render_invariant(entry_point, mode="math")
    inv_line = f"\ninvariant:\n{_INDENT}{inv}" if inv != "True" else ""
    return f"pre:\n{_INDENT}{pre}\npost:\n{_INDENT}{post}{inv_line}"


def render_entry_point(entry_point: str) -> str:
    """Structured, indented Dafny/JML-style contract for one entry point.

    Each keyword (requires, modifies, ensures, invariant, effects) is
    bold; its value starts on the next line indented one step.  Frame
    fields and event names are listed one per line for readability.
    Conjunctions are broken at `∧` boundaries into aligned lines.
    """
    from specsaver.types import ContractKind

    registry = get_registry()

    pre = render_precondition(entry_point, mode="math")
    post = render_postcondition(entry_point, mode="math")
    inv = render_invariant(entry_point, mode="math")

    writes_records = registry.list_by_entry_point(entry_point, ContractKind.WRITES)
    reads_records = registry.list_by_entry_point(entry_point, ContractKind.READS)
    effect_records = registry.list_by_entry_point(entry_point, ContractKind.EFFECT)

    writes_set: set[str] = set()
    reads_set: set[str] = set()
    for r in writes_records:
        try:
            writes_set |= {str(f) for f in r.func().writes}
        except Exception:
            pass
    for r in reads_records:
        try:
            reads_set |= {str(f) for f in r.func().reads}
        except Exception:
            pass

    eff_uses: set[str] = set()
    eff_opens: set[str] = set()
    eff_emits: set[str] = set()
    for r in effect_records:
        try:
            spec = r.func()
            eff_uses |= set(spec.uses)
            eff_opens |= set(spec.opens)
            eff_emits |= {e.name for e in spec.emits}
        except Exception:
            pass

    lines: list[str] = []

    # requires
    lines.append("[bold green]requires:[/]")
    lines.extend(_indent_lines(_break_conjunction(pre), 1))

    # modifies
    if writes_set or reads_set:
        lines.append("[bold green]modifies:[/]")
        if writes_set:
            lines.append(f"{_T1}[bold]writes:[/]")
            for f in sorted(writes_set):
                lines.append(f"{_T2}{f}")
        if reads_set:
            lines.append(f"{_T1}[bold]reads:[/]")
            for f in sorted(reads_set):
                lines.append(f"{_T2}{f}")

    # ensures
    lines.append("[bold green]ensures:[/]")
    lines.extend(_indent_lines(_break_conjunction(post), 1))

    # invariant
    if inv != "True":
        lines.append("[bold green]invariant:[/]")
        lines.extend(_indent_lines(_break_conjunction(inv), 1))

    # effects
    if eff_uses or eff_opens or eff_emits:
        lines.append("[bold green]effects:[/]")
        if eff_uses:
            for u in sorted(eff_uses):
                lines.append(f"{_T1}[bold]uses:[/] {u}")
        if eff_opens:
            for o in sorted(eff_opens):
                lines.append(f"{_T1}[bold]opens:[/] {o}")
        if eff_emits:
            lines.append(f"{_T1}[bold]emits:[/]")
            for e in sorted(eff_emits):
                lines.append(f"{_T2}{e}")

    return "\n".join(lines)


_T = "    "
_T1 = _T
_T2 = _T * 2


def _break_conjunction(formula: str) -> list[str]:
    """Split a `∧`-conjoined formula into aligned lines."""
    parts = [p.strip() for p in formula.split(" ∧ ")]
    if len(parts) <= 1:
        return [formula]
    return parts


def _indent_lines(parts: list[str], level: int) -> list[str]:
    prefix = _T * level
    if len(parts) == 1:
        return [f"{prefix}{parts[0]}"]
    result = [f"{prefix}{parts[0]}"]
    for p in parts[1:]:
        result.append(f"{prefix}  [dim]∧[/] {p}")
    return result


def render_all() -> str:
    """Render the full contract for every entry point in the registry."""
    registry = get_registry()
    entry_points: set[str] = set()
    for r in registry.list_all():
        if r.entry_point:
            entry_points.add(r.entry_point)
    if not entry_points:
        return "No contracts registered."
    sections: list[str] = []
    for ep in sorted(entry_points):
        sections.append(f"[{ep}]")
        sections.append(render_contract(ep))
        sections.append("")
    return "\n".join(sections)


# ---------------------------------------------------------------------------
# Internal: source extraction, conjunction assembly
# ---------------------------------------------------------------------------


def _render_conjunction(records: list[ContractRecord], mode: str) -> str:
    parts: list[str] = []
    for r in records:
        expr = _extract_return_expression(r.func)
        if expr is None:
            parts.append(r.qualname)
        else:
            rendered = _render_expr(ast.parse(expr, mode="eval").body, mode)
            parts.append(rendered)
    join = _CONJUNCTION_MATH if mode == "math" else _CONJUNCTION_PYTHON
    return join.join(parts)


def _extract_return_expression(func: Callable) -> str | None:
    """Parse func's source and return the text of its return expression."""
    try:
        source = textwrap.dedent(inspect.getsource(func))
    except (OSError, TypeError):
        return None
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    if not tree.body or not isinstance(
        tree.body[0], (ast.FunctionDef, ast.AsyncFunctionDef)
    ):
        return None
    for node in ast.walk(tree.body[0]):
        if isinstance(node, ast.Return) and node.value is not None:
            return ast.unparse(node.value)
    return None


# ---------------------------------------------------------------------------
# AST → string rendering (two modes: python, math)
# ---------------------------------------------------------------------------


def _render_expr(node: ast.expr, mode: str) -> str:
    if mode == "math":
        return _MathRenderer().visit(node)
    return _PythonRenderer().visit(node)


class _BaseRenderer(ast.NodeVisitor):
    def generic_visit(self, node):
        return ast.unparse(node)

    @staticmethod
    def _is_quantifier_call(node: ast.Call, name: str) -> bool:
        return isinstance(node.func, ast.Name) and node.func.id == name

    @staticmethod
    def _lambda_arg(node: ast.Call) -> ast.arg:
        lam = node.args[1]
        assert isinstance(lam, ast.Lambda)
        return lam.args.args[0]

    @staticmethod
    def _lambda_body(node: ast.Call) -> ast.expr:
        lam = node.args[1]
        assert isinstance(lam, ast.Lambda)
        return lam.body

    def _visit_old(self, node: ast.Call) -> str:
        inner = node.args[0] if node.args else node.func
        return f"old({ast.unparse(inner)})"

    def _render_bool_op(self, node: ast.BoolOp, and_word: str, paren_word: str) -> str:
        parts = [self.visit(v) for v in node.values]
        op = and_word if isinstance(node.op, ast.And) else paren_word
        pieces = []
        for v, p in zip(node.values, parts, strict=True):
            if isinstance(v, ast.BoolOp):
                pieces.append(f"({p})")
            else:
                pieces.append(p)
        return op.join(pieces)


class _PythonRenderer(_BaseRenderer):
    """Render as close to verbatim Python as possible."""

    def visit_BoolOp(self, node: ast.BoolOp) -> str:
        return self._render_bool_op(node, " and ", " or ")

    def visit_UnaryOp(self, node: ast.UnaryOp) -> str:
        if isinstance(node.op, ast.Not):
            return f"not ({self.visit(node.operand)})"
        return ast.unparse(node)

    def visit_Call(self, node: ast.Call) -> str:
        if self._is_quantifier_call(node, "forall"):
            domain = self.visit(node.args[0])
            body = self.visit(self._lambda_body(node))
            param = self._lambda_arg(node).arg
            return f"forall({domain}, lambda {param}: {body})"
        if self._is_quantifier_call(node, "exists"):
            domain = self.visit(node.args[0])
            body = self.visit(self._lambda_body(node))
            param = self._lambda_arg(node).arg
            return f"exists({domain}, lambda {param}: {body})"
        if self._is_old_call(node):
            return self._visit_old(node)
        return ast.unparse(node)

    def _is_old_call(self, node: ast.Call) -> bool:
        if isinstance(node.func, ast.Name) and node.func.id == "old":
            return bool(node.args)
        if isinstance(node.func, ast.Attribute) and isinstance(
            node.func.value, ast.Name
        ):
            return node.func.value.id == "old"
        return False


class _MathRenderer(_BaseRenderer):
    """Render using mathematical/logical notation."""

    def visit_BoolOp(self, node: ast.BoolOp) -> str:
        return self._render_bool_op(node, " ∧ ", " ∨ ")

    def visit_UnaryOp(self, node: ast.UnaryOp) -> str:
        if isinstance(node.op, ast.Not):
            return f"¬({self.visit(node.operand)})"
        return ast.unparse(node)

    def visit_Compare(self, node: ast.Compare) -> str:
        left = self.visit(node.left)
        parts: list[str] = []
        for op, comp in zip(node.ops, node.comparators, strict=True):
            right = self.visit(comp)
            parts.append(f"{left} {_math_op(op)} {right}")
            left = right
        return " ∧ ".join(parts) if len(parts) > 1 else parts[0]

    def visit_BinOp(self, node: ast.BinOp) -> str:
        left = self.visit(node.left)
        right = self.visit(node.right)
        return f"{left} {_bin_op(node.op)} {right}"

    def visit_Call(self, node: ast.Call) -> str:
        if self._is_quantifier_call(node, "forall"):
            domain = self.visit(node.args[0])
            body = self.visit(self._lambda_body(node))
            param = self._lambda_arg(node).arg
            return (
                f"[#FFBF00]∀[/] {param} "
                f"[bright_blue]∈[/] [bright_blue]{domain}[/]. {body}"
            )
        if self._is_quantifier_call(node, "exists"):
            domain = self.visit(node.args[0])
            body = self.visit(self._lambda_body(node))
            param = self._lambda_arg(node).arg
            return (
                f"[#FFBF00]∃[/] {param} "
                f"[bright_blue]∈[/] [bright_blue]{domain}[/]. {body}"
            )
        if self._is_old_call(node):
            return self._visit_old(node)
        return ast.unparse(node)

    def _is_old_call(self, node: ast.Call) -> bool:
        if isinstance(node.func, ast.Name) and node.func.id == "old":
            return bool(node.args)
        if isinstance(node.func, ast.Attribute) and isinstance(
            node.func.value, ast.Name
        ):
            return node.func.value.id == "old"
        return False

    def visit_Constant(self, node: ast.Constant) -> str:
        if node.value is True:
            return "⊤"
        if node.value is False:
            return "⊥"
        return ast.unparse(node)

    def visit_Attribute(self, node: ast.Attribute) -> str:
        base = self.visit(node.value)
        return f"{base}.{node.attr}"

    def visit_Subscript(self, node: ast.Subscript) -> str:
        value = self.visit(node.value)
        subscript = self.visit(node.slice)
        return f"{value}[{subscript}]"

    def visit_Name(self, node: ast.Name) -> str:
        return node.id


# ---------------------------------------------------------------------------
# Operator maps
# ---------------------------------------------------------------------------


def _math_op(op: ast.cmpop) -> str:
    if isinstance(op, ast.Gt):
        return ">"
    if isinstance(op, ast.Lt):
        return "<"
    if isinstance(op, ast.GtE):
        return "≥"
    if isinstance(op, ast.LtE):
        return "≤"
    if isinstance(op, ast.Eq):
        return "="
    if isinstance(op, ast.NotEq):
        return "≠"
    if isinstance(op, ast.In):
        return "∈"
    if isinstance(op, ast.NotIn):
        return "∉"
    return ast.unparse(op)


def _bin_op(op: ast.operator) -> str:
    if isinstance(op, ast.Add):
        return "+"
    if isinstance(op, ast.Sub):
        return "−"
    if isinstance(op, ast.Mult):
        return "·"
    if isinstance(op, ast.Div):
        return "÷"
    if isinstance(op, ast.FloorDiv):
        return "//"
    if isinstance(op, ast.Mod):
        return "mod"
    return ast.unparse(op)
