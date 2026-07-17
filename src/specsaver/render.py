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
from specsaver.types import ContractKind

_CONJUNCTION_PYTHON = " and "
_CONJUNCTION_MATH = " ∧ "
_CONJ_RICH = " [#FFBF00]∧[/] "
_INDENT = "      "


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def render_precondition(feature: str, mode: str = "python") -> str:
    records = get_registry().list_by_feature_and_kind(
        feature, ContractKind.PRECONDITION
    )
    if not records:
        return "True"
    return _render_conjunction(records, mode)


def render_postcondition(feature: str, mode: str = "python") -> str:
    records = get_registry().list_by_feature_and_kind(
        feature, ContractKind.POSTCONDITION
    )
    if not records:
        return "True"
    return _render_conjunction(records, mode)


def render_invariant(feature: str, mode: str = "python") -> str:
    records = get_registry().list_by_feature_and_kind(
        feature, ContractKind.INVARIANT
    )
    if not records:
        return "True"
    return _render_conjunction(records, mode)


def render_exceptional(feature: str, mode: str = "python") -> str:
    records = get_registry().list_by_feature_and_kind(
        feature, ContractKind.EXCEPTIONAL
    )
    if not records:
        return ""
    parts: list[str] = []
    for r in records:
        exc_name = getattr(r.func, "_specsaver_exc_type", "Exception")
        expr = _extract_return_expression(r.func)
        if expr:
            rendered = _render_expr(ast.parse(expr, mode="eval").body, mode)
            parts.append(f"{exc_name}: {rendered}")
        else:
            parts.append(exc_name)
    join = _CONJUNCTION_MATH if mode == "math" else _CONJUNCTION_PYTHON
    return join.join(parts)


def render_contract(feature: str) -> str:
    pre = render_precondition(feature, mode="math")
    post = render_postcondition(feature, mode="math")
    inv = render_invariant(feature, mode="math")
    exc = render_exceptional(feature, mode="math")
    inv_line = f"\ninvariant:\n{_INDENT}{inv}" if inv != "True" else ""
    exc_line = f"\nexceptions:\n{_INDENT}{exc}" if exc else ""
    return f"pre:\n{_INDENT}{pre}\npost:\n{_INDENT}{post}{inv_line}{exc_line}"


def render_entry_point(feature: str) -> str:
    registry = get_registry()
    pre = render_precondition(feature, mode="math")
    post = render_postcondition(feature, mode="math")
    inv = render_invariant(feature, mode="math")
    writes_records = registry.list_by_feature_and_kind(feature, ContractKind.WRITES)
    reads_records = registry.list_by_feature_and_kind(feature, ContractKind.READS)
    effect_records = registry.list_by_feature_and_kind(feature, ContractKind.EFFECT)

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
    lines.append("[bold green]requires:[/]")
    lines.extend(_indent_lines(_break_conjunction(pre), 1, " ∧ "))
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
    lines.append("[bold green]ensures:[/]")
    lines.extend(_indent_lines(_break_conjunction(post), 1, " ∧ "))
    if inv != "True":
        lines.append("[bold green]invariant:[/]")
        lines.extend(_indent_lines(_break_conjunction(inv), 1, " ∧ "))
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
    exc = render_exceptional(feature, mode="math")
    if exc:
        lines.append("[bold green]exceptions:[/]")
        lines.extend(_indent_lines(_break_conjunction(exc), 1, " ∧ "))
    return "\n".join(lines)


def render_contract_from_object(contract, title: str = "") -> str:
    """Render a single Contract object directly."""
    from specsaver.contract_model import Contract
    if not isinstance(contract, Contract):
        return ""
    lines: list[str] = [""]
    _conj = _CONJ_RICH

    if contract.state_schema:
        from rich.markup import escape
        lines.append("[bold green]state:[/]")
        for name, field in contract.state_schema.items():
            prov = field.provenance
            color = {"observed": "green", "derived": "yellow", "ghost": "dim"}
            lines.append(
                f"{_T1}{name}: {escape(field.type_hint)} "
                f"[{color.get(prov, 'dim')}]← {prov}[/]"
            )

    pre = _render_predicate_list(contract.requires, "math")
    if pre:
        q = _render_quantifier_header(contract.requires, "math",
                                      args_type=contract.args_type)
        label = f"[bold green]requires:[/] {q}" if q else "[bold green]requires:[/]"
        lines.append(label)
        lines.extend(_indent_lines(pre, 1, _conj))
    post = _render_predicate_list(contract.ensures, "math")
    if post:
        q = _render_quantifier_header(contract.ensures, "math",
                                      kind="ensures",
                                      args_type=contract.args_type)
        label = f"[bold green]ensures:[/] {q}" if q else "[bold green]ensures:[/]"
        lines.append(label)
        lines.extend(_indent_lines(post, 1, _conj))

    if contract.writes or contract.reads:
        lines.append("[bold green]modifies:[/]")
        if contract.writes:
            lines.append(f"{_T1}[bold green]writes:[/]")
            for f in sorted(contract.writes):
                lines.append(f"{_T2}{f.replace("[", r"\[")}")
        if contract.reads:
            lines.append(f"{_T1}[bold green]reads:[/]")
            for f in sorted(contract.reads):
                lines.append(f"{_T2}{f.replace("[", r"\[")}")

    inv = _render_predicate_list(contract.invariants, "math")
    if inv:
        q = _render_quantifier_header(contract.invariants, "math")
        label = f"[bold green]invariant:[/] {q}" if q else "[bold green]invariant:[/]"
        lines.append(label)
        lines.extend(_indent_lines(inv, 1, _conj))

    if contract.derives:
        lines.append("[bold green]derived:[/]")
        for name, fn in contract.derives.items():
            expr_src, param_names = _extract_return_expression_with_params(fn)
            if expr_src:
                rendered = _render_normalized(expr_src, param_names, "math")
                lines.append(f"{_T1}{name} ≜ {rendered}")

    exc_parts = _render_exception_dict(contract.exceptions, "math",
                                        args_type=contract.args_type)
    if exc_parts:
        lines.append("[bold green]exceptions:[/]")
        lines.extend(exc_parts)
    lines.append("")
    return "\n".join(lines)


_T = "    "
_T1 = _T
_T2 = _T * 2
_T3 = _T * 3


def _break_conjunction(formula: str) -> list[str]:
    """Split a `∧`-conjoined formula into aligned lines."""
    parts = [p.strip() for p in formula.split(" ∧ ")]
    if len(parts) <= 1:
        return [formula]
    return parts


def _indent_lines(parts: list[str], level: int, conj: str = " ∧ ") -> list[str]:
    prefix = _T * level
    if len(parts) == 1:
        return [f"{prefix}{parts[0]}"]
    result = [f"{prefix}{parts[0]}"]
    for p in parts[1:]:
        result.append(f"{prefix}{conj}{p}")
    return result


def render_all() -> str:
    """Render the full contract for every feature in the registry."""
    registry = get_registry()
    features: set[str] = set()
    for r in registry.list_all():
        if r.feature:
            features.add(r.feature)
    if not features:
        return "No contracts registered."
    sections: list[str] = []
    for f in sorted(features):
        sections.append(f"[{f}]")
        sections.append(render_contract(f))
        sections.append("")
    return "\n".join(sections)


# ---------------------------------------------------------------------------
# Internal: source extraction, conjunction assembly
# ---------------------------------------------------------------------------


def _render_predicate_list(predicates: list, mode: str) -> list[str]:
    """Return one string per predicate, not joined — the caller formats alignment."""
    if not predicates:
        return []
    rendered: list[str] = []
    for p in predicates:
        expr_src, param_names = _extract_return_expression_with_params(p)
        if expr_src is None:
            rendered.append(getattr(p, "__qualname__", str(p)))
        else:
            rendered.append(_render_normalized(expr_src, param_names, mode))
    return rendered


def _render_quantifier_header(predicates: list, mode: str,
                              kind: str = "forall",
                              args_type: type | None = None) -> str | None:
    """Extract the shared quantifier scope from the first predicate's parameters."""
    if not predicates:
        return None
    _, param_names = _extract_return_expression_with_params(predicates[0])
    if not param_names:
        return None
    canonical = _canonical_param_names(param_names)
    if args_type is not None and hasattr(args_type, "__dataclass_fields__"):
        arg_fields = [
            f"{f.name}: {_type_str(f.type)}"
            for f in args_type.__dataclass_fields__.values()
        ]
        canonical = [p for p in canonical if p != "args"] + arg_fields
    if kind == "ensures" and len(canonical) >= 2:
        pre_vars = [canonical[0]]
        post_vars = [canonical[1], canonical[2]]
        for a in canonical[3:]:
            pre_vars.append(a)
        pre_s = f"[#FFBF00]∀[/] {', '.join(pre_vars)}."
        post_s = f"[#FFBF00]∃[/] {', '.join(post_vars)}."
        return f"{pre_s}\n{_T}{post_s}"
    return f"[#FFBF00]∀[/] {', '.join(canonical)}."


def _type_str(typ) -> str:
    """Pretty-print a type annotation."""
    origin = getattr(typ, "__origin__", None)
    if origin is not None:
        args = ", ".join(_type_str(a) for a in typ.__args__)
        name = getattr(origin, "__name__", str(origin))
        return f"{name}[{args}]"
    return getattr(typ, "__name__", str(typ))


def _canonical_param_names(param_names: tuple[str, ...]) -> list[str]:
    """Map lambda parameter names to canonical contract names, skipping 'args'."""
    n = len(param_names)
    if n == 1:
        return ["state"]
    if n == 2:
        return ["state"]
    if n >= 4:
        first = param_names[0]
        if first in ("old_s", "old_state", "prev"):
            if n >= 5:
                return ["old(state)", "result", "state", param_names[4]]
            return ["old(state)", "result", "state"]
        else:
            return ["old(state)", "args", param_names[2], "state"]
    return [p for p in param_names if p not in ("args",)]


def _render_exception_dict(exceptions: list, mode: str,
                           args_type: type | None = None) -> list[str]:
    parts: list[str] = []
    for exit_ in exceptions:
        exc_type = exit_.raises
        lines: list[str] = []
        # Build spilled-out arg types for the quantifier
        arg_vars = ["old(state)"]
        if args_type is not None and hasattr(args_type, "__dataclass_fields__"):
            arg_vars += [
                f"{f.name}: {_type_str(f.type)}"
                for f in args_type.__dataclass_fields__.values()
            ]
        else:
            arg_vars.append("args")
        lines.append(
            f"{_T1}[#FFBF00]∀[/] {', '.join(arg_vars)}."
        )
        if exit_.when:
            lines.append(f"{_T1}[bold green]when:[/]")
            for fn in exit_.when:
                expr_src, pn = _extract_return_expression_with_params(fn)
                if expr_src:
                    r = _render_normalized(expr_src, pn, mode)
                    # when is about the pre-state — if the lambda uses bare
                    # 'state' (2-param), rewrite to old(state) for display
                    if len(pn) == 2:
                        r = r.replace("state.", "old(state).")
                    lines.append(f"{_T2}{r}")
        lines.append(
            f"{_T1}[bold green]raises:[/] exc: "
            f"[bold steel_blue3]{exc_type.__name__}[/]"
        )
        lines.append(
            f"{_T1}[bold green]ensures:[/] "
            f"[#FFBF00]∃[/] exc, state."
        )
        if exit_.ensures:
            pred_parts: list[str] = []
            for fn in exit_.ensures:
                expr_src, pn = _extract_return_expression_with_params(fn)
                if expr_src:
                    pred_parts.append(_render_normalized(expr_src, pn, mode))
            lines.extend(_indent_lines(pred_parts, 2, _CONJ_RICH))
        else:
            lines.append(f"{_T2}[#FFBF00]⊤[/]")
        parts.append("\n".join(lines))
    return parts


def _normalize_var_names(text: str, param_names: tuple[str, ...]) -> str:
    """Replace lambda parameter names with canonical contract notation."""
    if not param_names:
        return text
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError:
        return text
    normalized = _rewrite_names(tree.body, param_names)
    ast.fix_missing_locations(normalized)
    return ast.unparse(normalized)


def _rewrite_names(node, param_names: tuple[str, ...]) -> ast.AST:
    """Copy *node*, rewriting parameter names using a clean recursive pass."""
    n = len(param_names)
    # Only 4-param signatures (postcondition/exception) treat param 0 as old state
    is_multistate = n >= 4
    pre_state = param_names[0] if is_multistate else None
    args_name = param_names[1] if n >= 2 else None
    post_state = param_names[3] if n >= 4 else None

    def _walk(n):
        if isinstance(n, ast.Attribute):
            if n.attr in ("observed", "derived"):
                return _walk(n.value)
            if isinstance(n.value, ast.Name) and n.value.id == args_name:
                return ast.Name(id=n.attr, ctx=n.value.ctx)
            val = _walk(n.value)
            if isinstance(val, ast.Name) and val.id == pre_state:
                val = _make_old_call()
            elif isinstance(val, ast.Name) and val.id == post_state:
                val = ast.Name(id="state", ctx=val.ctx)
            return ast.Attribute(value=val, attr=n.attr, ctx=n.ctx)
        if isinstance(n, ast.Name):
            return ast.Name(id=n.id, ctx=n.ctx)
        # Copy other nodes recursively
        kwargs = {}
        for field_name, old_value in ast.iter_fields(n):
            if isinstance(old_value, list):
                kwargs[field_name] = [_rewrite_names(v, param_names) for v in old_value]
            elif isinstance(old_value, ast.AST):
                kwargs[field_name] = _walk(old_value)
            else:
                kwargs[field_name] = old_value
        return n.__class__(**kwargs)
    return _walk(node)


def _render_normalized(expr_src: str, param_names: tuple[str, ...],
                       mode: str) -> str:
    """Parse, normalize variable names, and render."""
    tree = ast.parse(expr_src, mode="eval")
    assert isinstance(tree.body, ast.expr)
    normalized = _rewrite_names(tree.body, param_names)
    ast.fix_missing_locations(normalized)
    return _render_expr(normalized, mode)


def _make_old_call() -> ast.Call:
    return ast.Call(
        func=ast.Name(id="old", ctx=ast.Load()),
        args=[ast.Name(id="state", ctx=ast.Load())],
        keywords=[],
    )


def _extract_return_expression_with_params(
    func: Callable,
) -> tuple[str | None, tuple[str, ...]]:
    """Like _extract_return_expression but also returns lambda parameter names."""
    try:
        source = textwrap.dedent(inspect.getsource(func))
    except (OSError, TypeError):
        return None, ()
    stripped = source.strip()
    # Strip trailing comma and any inline comment from dict-literal lambdas
    if "#" in stripped:
        stripped = stripped[:stripped.index("#")].strip()
    stripped = stripped.rstrip(",")
    idx = stripped.find("lambda ")
    if idx > 0:
        stripped = stripped[idx:]
    try:
        tree = ast.parse(stripped, mode="eval")
        if isinstance(tree.body, ast.Lambda):
            param_names = tuple(a.arg for a in tree.body.args.args)
            return ast.unparse(tree.body.body), param_names
    except SyntaxError:
        pass
    # Fall back to old extraction for named functions
    expr = _extract_return_expression(func)
    return expr, ()


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
    # Lambdas in dict literals get source like "Key: lambda x: expr,"
    # — strip the key prefix to isolate the lambda expression.
    stripped = source.strip().rstrip(",")
    # Find the lambda keyword in the source and start from there
    idx = stripped.find("lambda ")
    if idx > 0:
        stripped = stripped[idx:]
    try:
        tree = ast.parse(stripped, mode="eval")
    except SyntaxError:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return None
        if not tree.body:
            return None
        if isinstance(tree.body[0], ast.Expr) and isinstance(
            tree.body[0].value, ast.Lambda
        ):
            return ast.unparse(tree.body[0].value.body)
        if not isinstance(tree.body[0], (ast.FunctionDef, ast.AsyncFunctionDef)):
            return None
        for node in ast.walk(tree.body[0]):
            if isinstance(node, ast.Return) and node.value is not None:
                return ast.unparse(node.value)
        return None
    if isinstance(tree.body, ast.Lambda):
        return ast.unparse(tree.body.body)
    return ast.unparse(tree.body)


# ---------------------------------------------------------------------------
# AST → string rendering (two modes: python, math)
# ---------------------------------------------------------------------------


def _type_name(node: ast.expr) -> str:
    """Extract the type name from an isinstance second argument."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Tuple):
        return " | ".join(_type_name(e) for e in node.elts)
    return ast.unparse(node)


def _render_expr(node: ast.expr, mode: str) -> str:
    if mode == "math":
        return _MathRenderer().visit(node)
    return _PythonRenderer().visit(node)


class _BaseRenderer(ast.NodeVisitor):
    def generic_visit(self, node):
        text = ast.unparse(node)
        return text.replace("[", r"\[")

    @staticmethod
    def _is_quantifier_call(node: ast.Call, name: str) -> bool:
        return isinstance(node.func, ast.Name) and node.func.id == name

    @staticmethod
    @staticmethod
    def _is_implies_call(node: ast.Call) -> bool:
        return isinstance(node.func, ast.Name) and node.func.id == "implies"

    @staticmethod
    def _is_isinstance_call(node: ast.Call) -> bool:
        return isinstance(node.func, ast.Name) and node.func.id == "isinstance"

    @staticmethod
    def _is_all_call(node: ast.Call) -> bool:
        return isinstance(node.func, ast.Name) and node.func.id == "all"

    @staticmethod
    def _generator_arg(node: ast.Call) -> tuple:
        gen = node.args[0]
        assert isinstance(gen, ast.GeneratorExp)
        comp = gen.generators[0]
        return comp.target, comp.iter, comp.ifs, gen.elt

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
        if isinstance(node.op, ast.And):
            op = f" [#FFBF00]{and_word}[/] "
        else:
            op = f" [#FFBF00]{paren_word}[/] "
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
        if self._is_isinstance_call(node):
            return f"{self.visit(node.args[0])} : [bold]{_type_name(node.args[1])}[/]"
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
        if self._is_implies_call(node):
            p = self.visit(node.args[0])
            q = self.visit(node.args[1])
            return f"({p} → {q})"
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
        return self._render_bool_op(node, "∧", "∨")

    def visit_UnaryOp(self, node: ast.UnaryOp) -> str:
        if isinstance(node.op, ast.Not):
            return f"[#FFBF00]¬[/]({self.visit(node.operand)})"
        return ast.unparse(node)

    def visit_Compare(self, node: ast.Compare) -> str:
        left = self.visit(node.left)
        parts: list[str] = []
        for op, comp in zip(node.ops, node.comparators, strict=True):
            right = self.visit(comp)
            parts.append(f"{left} {_math_op(op)} {right}")
            left = right
        result = " ∧ ".join(parts) if len(parts) > 1 else parts[0]
        # Wrap is/isnot compares so a = None = b = None reads as (a = None) = (b = None)
        if any(isinstance(o, (ast.Is, ast.IsNot)) for o in node.ops):
            result = f"({result})"
        return result

    def visit_BinOp(self, node: ast.BinOp) -> str:
        left = self.visit(node.left)
        right = self.visit(node.right)
        return f"{left} {_bin_op(node.op)} {right}"

    def visit_Call(self, node: ast.Call) -> str:
        if self._is_isinstance_call(node):
            return (
                f"{self.visit(node.args[0])} : "
                f"[bright_blue]{_type_name(node.args[1])}[/]"
            )
        if self._is_all_call(node):
            target, iter_, ifs, body = self._generator_arg(node)
            param = self.visit(target)
            domain = self.visit(iter_)
            body_s = self.visit(body)
            head = f"[#FFBF00]∀[/] {param} [bright_blue]∈[/] [bright_blue]{domain}[/]"
            if ifs:
                conds = " ∧ ".join(self.visit(c) for c in ifs)
                head += f" , {conds}"
            return f"{head}. {body_s}"
        if self._is_quantifier_call(node, "forall"):
            domain = self.visit(node.args[0])
            body = self.visit(self._lambda_body(node))
            param = self._lambda_arg(node).arg
            return (
                f"[#FFBF00]∀[/] {param} "
                f"[#FFBF00]∈[/] [bright_blue]{domain}[/]. {body}"
            )
        if self._is_quantifier_call(node, "exists"):
            domain = self.visit(node.args[0])
            body = self.visit(self._lambda_body(node))
            param = self._lambda_arg(node).arg
            return (
                f"[#FFBF00]∃[/] {param} "
                f"[#FFBF00]∈[/] [bright_blue]{domain}[/]. {body}"
            )
        if self._is_implies_call(node):
            p = self.visit(node.args[0])
            q = self.visit(node.args[1])
            return f"({p} [#FFBF00]⇒[/] {q})"
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
            return "[#FFBF00]⊤[/]"
        if node.value is False:
            return "[#FFBF00]⊥[/]"
        return ast.unparse(node)

    def visit_Attribute(self, node: ast.Attribute) -> str:
        base = self.visit(node.value)
        return f"{base}.{node.attr}"

    def visit_Subscript(self, node: ast.Subscript) -> str:
        value = self.visit(node.value)
        subscript = self.visit(node.slice)
        return f"{value}\\[{subscript}]"

    def visit_Name(self, node: ast.Name) -> str:
        return node.id


# ---------------------------------------------------------------------------
# Operator maps
# ---------------------------------------------------------------------------


def _math_op(op: ast.cmpop) -> str:
    if isinstance(op, ast.Gt):
        return "[#FFBF00]>[/]"
    if isinstance(op, ast.Lt):
        return "[#FFBF00]<[/]"
    if isinstance(op, ast.GtE):
        return "[#FFBF00]≥[/]"
    if isinstance(op, ast.LtE):
        return "[#FFBF00]≤[/]"
    if isinstance(op, ast.Eq):
        return "[#FFBF00]=[/]"
    if isinstance(op, ast.NotEq):
        return "[#FFBF00]≠[/]"
    if isinstance(op, ast.In):
        return "[bright_blue]∈[/]"
    if isinstance(op, ast.NotIn):
        return "[bright_blue]∉[/]"
    if isinstance(op, ast.Is):
        return "[#FFBF00]=[/]"
    if isinstance(op, ast.IsNot):
        return "[#FFBF00]≠[/]"
    return ast.unparse(op)


def _bin_op(op: ast.operator) -> str:
    if isinstance(op, ast.Add):
        return "[#FFBF00]+[/]"
    if isinstance(op, ast.Sub):
        return "[#FFBF00]−[/]"
    if isinstance(op, ast.Mult):
        return "[#FFBF00]·[/]"
    if isinstance(op, ast.Div):
        return "[#FFBF00]÷[/]"
    if isinstance(op, ast.FloorDiv):
        return "//"
    if isinstance(op, ast.Mod):
        return "[#FFBF00]mod[/]"
    return ast.unparse(op)
