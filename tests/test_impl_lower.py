"""Phase 1: pure Python fragment → SnakeletExn AST lowerer tests."""

from specsaver.lower.impl_lower import emit_snakelet, lower_func


def test_add_one():
    expr = lower_func("def f(x):\n    y = x + 1\n    return y\n")
    coq = emit_snakelet(expr)
    assert "Let" in coq
    assert "AddOp" in coq
    assert "Var \"x\"" in coq
    assert "LitInt 1" in coq


def test_absolute():
    expr = lower_func("def f(x):\n    if x < 0:\n"
                        "        return 0 - x\n    return x\n")
    coq = emit_snakelet(expr)
    assert "If" in coq
    assert "LtOp" in coq
    assert "SubOp" in coq


def test_simple_return():
    expr = lower_func("def f(x):\n    return x\n")
    coq = emit_snakelet(expr)
    assert coq == 'Var "x"'


def test_comparison():
    expr = lower_func("def f(x):\n    if x == 0:\n"
                        "        return 1\n    return 0\n")
    coq = emit_snakelet(expr)
    assert "EqOp" in coq
    assert "If" in coq


def test_integer_literal():
    expr = lower_func("def f():\n    return 42\n")
    coq = emit_snakelet(expr)
    assert "LitInt 42" in coq
