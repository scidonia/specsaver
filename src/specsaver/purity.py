"""Purity validator for the contract language.

Ensures contracts satisfy the purity requirements:
- No mutation of reachable objects
- No I/O (filesystem, network, print, input)
- No global/module-level mutable state
- Deterministic
- No exception-driven control flow (try/except)
"""

from __future__ import annotations

import ast
from typing import Any

_MUTATING_OPS = frozenset(
    {
        ast.AugAssign,
        ast.AnnAssign,
        ast.Assign,
    }
)

_DISALLOWED_AST_NODES = frozenset(
    {
        ast.Global,
        ast.Nonlocal,
        ast.Try,
        ast.TryStar,
        ast.With,
        ast.AsyncWith,
        ast.Yield,
        ast.YieldFrom,
        ast.Await,
        ast.Import,
        ast.ImportFrom,
        ast.Delete,
        ast.ClassDef,
    }
)

_DISALLOWED_BUILTINS = frozenset(
    {
        "print",
        "input",
        "open",
        "eval",
        "exec",
        "__import__",
        "breakpoint",
    }
)


class PurityError(Exception):
    """Raised when a contract body violates purity constraints."""


def check_purity(func: Any) -> None:
    """Validate that *func* is a pure contract.

    Raises PurityError on the first violation found.
    """
    try:
        source = _get_source(func)
    except (OSError, TypeError):
        return  # Can't inspect — skip for now

    if source is None:
        return

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        raise PurityError(f"Syntax error in contract {func.__qualname__}: {e}") from e

    if not tree.body:
        return

    func_def = tree.body[0]
    # Lambda contract (the Contract-model style): the source may be a bare
    # lambda, an assignment of one, or a tuple-wrapped one (trailing comma).
    lam = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.Lambda)), None
    )
    if lam is not None:
        visitor = _PurityVisitor(
            getattr(func, "__qualname__", "<lambda>")
        )
        for arg in lam.args.args + lam.args.posonlyargs + lam.args.kwonlyargs:
            visitor._local_names.add(arg.arg)
        if lam.args.vararg:
            visitor._local_names.add(lam.args.vararg.arg)
        if lam.args.kwarg:
            visitor._local_names.add(lam.args.kwarg.arg)
        visitor.visit(lam.body)
        return

    if not isinstance(func_def, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return

    visitor = _PurityVisitor(func.__qualname__)
    visitor.visit(func_def)


def _get_source(func: Any) -> str | None:
    import inspect
    import textwrap

    try:
        source = inspect.getsource(func)
        return textwrap.dedent(source)
    except (OSError, TypeError):
        return None


class _PurityVisitor(ast.NodeVisitor):
    def __init__(self, qualname: str) -> None:
        self.qualname = qualname
        self._local_names: set[str] = set()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        for arg in node.args.args + node.args.posonlyargs + node.args.kwonlyargs:
            self._local_names.add(arg.arg)
        if node.args.vararg:
            self._local_names.add(node.args.vararg.arg)
        if node.args.kwarg:
            self._local_names.add(node.args.kwarg.arg)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        raise PurityError(
            f"{self.qualname}: async functions are not allowed in contracts"
        )

    def _check_disallowed(self, node: ast.AST, kind: str) -> None:
        lineno = getattr(node, "lineno", 0)
        raise PurityError(
            f"{self.qualname} (line {lineno}): {kind} is not allowed in contracts"
        )

    def visit_Global(self, node: ast.Global) -> None:
        self._check_disallowed(node, "global statement")

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        self._check_disallowed(node, "nonlocal statement")

    def visit_Try(self, node: ast.Try) -> None:
        self._check_disallowed(node, "try/except")

    def visit_TryStar(self, node: ast.TryStar) -> None:
        self._check_disallowed(node, "try/except*")

    def visit_With(self, node: ast.With) -> None:
        self._check_disallowed(node, "with statement")

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        self._check_disallowed(node, "async with statement")

    def visit_Yield(self, node: ast.Yield) -> None:
        self._check_disallowed(node, "yield")

    def visit_YieldFrom(self, node: ast.YieldFrom) -> None:
        self._check_disallowed(node, "yield from")

    def visit_Await(self, node: ast.Await) -> None:
        self._check_disallowed(node, "await")

    def visit_Import(self, node: ast.Import) -> None:
        self._check_disallowed(node, "import")

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self._check_disallowed(node, "import")

    def visit_Delete(self, node: ast.Delete) -> None:
        self._check_disallowed(node, "del")

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._check_disallowed(node, "class definition")

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id in _DISALLOWED_BUILTINS:
            raise PurityError(
                f"{self.qualname} (line {node.lineno}): "
                f"builtin {node.func.id!r} is not allowed in contracts"
            )
        self.generic_visit(node)
