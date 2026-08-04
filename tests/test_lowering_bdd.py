"""BDD tests for implementation lowering: execute Python vs SnakeletExn.

The lowered program must produce the same observable results as the
original Python function for the same inputs.
"""

import pytest

from specsaver.lower.impl_lower import (
    SBinOp, SCall, SIf, SInt, SLet, SLoad, SRaise, SRec, SStore,
    SString, STry, SUnit, SVar, emit_snakelet, lower_func,
)


class SnInterp:
    """Tree-walking interpreter for lowered SnakeletExn ASTs."""

    def __init__(self):
        self.heap: dict[int, object] = {}
        self.fuel = 10000

    def eval(self, node, env=None):
        if env is None:
            env = {}
        self.fuel -= 1
        if self.fuel <= 0:
            raise RuntimeError("out of fuel")

        if isinstance(node, SInt): return node.value
        if isinstance(node, SString): return node.value
        if isinstance(node, SUnit): return None
        if isinstance(node, SVar): return env[node.name]
        if isinstance(node, SRec):
            return {k: self.eval(v, env) for k, v in node.fields}
        if isinstance(node, SLet):
            val = self.eval(node.e1, env)
            env2 = dict(env)
            env2[node.var] = val
            return self.eval(node.e2, env2)
        if isinstance(node, SBinOp):
            left = self.eval(node.left, env)
            right = self.eval(node.right, env)
            return self._binop(node.op, left, right)
        if isinstance(node, SIf):
            cond = self.eval(node.cond, env)
            if cond is True:
                return self.eval(node.then_body, env)
            elif cond is False:
                return self.eval(node.else_body, env)
            raise TypeError(f"If condition not boolean: {cond}")
        if isinstance(node, SRaise):
            payload = self.eval(node.payload, env)
            raise Exception(payload)
        if isinstance(node, STry):
            try:
                return self.eval(node.body, env)
            except Exception as e:
                env2 = dict(env)
                env2[node.handler_var] = e
                return self.eval(node.handler_body, env2)
        if isinstance(node, SLoad):
            loc = self.eval(node.loc, env)
            if isinstance(loc, tuple) and loc[0] == 'loc':
                return self.heap.get(loc[1])
            return None
        if isinstance(node, SStore):
            loc = self.eval(node.loc, env)
            val = self.eval(node.val, env)
            if isinstance(loc, tuple) and loc[0] == 'loc':
                self.heap[loc[1]] = val
            return None
        if isinstance(node, SCall):
            fname = node.fn
            args = [self.eval(a, env) for a in node.args]
            return self._call(fname, args)
        raise NotImplementedError(f"no eval for {type(node).__name__}")

    def _binop(self, op, left, right):
        if op == "AddOp": return left + right
        if op == "SubOp": return left - right
        if op == "MulOp": return left * right
        if op == "DivOp": return left // right
        if op == "ModOp": return left % right
        if op == "EqOp": return left == right
        if op == "NeOp": return left != right
        if op == "LtOp": return left < right
        if op == "LeOp": return left <= right
        if op == "GtOp": return left > right
        if op == "GeOp": return left >= right
        if op == "AndOp": return left and right
        if op == "OrOp": return left or right
        raise NotImplementedError(f"binop {op}")

    def _call(self, fname, args):
        if fname == "dict_lookup_str":
            key, d = args
            if isinstance(d, dict):
                return d.get(key)
            return None
        if fname == "dict_insert_str":
            key, v, d = args
            if isinstance(d, dict):
                d2 = dict(d)
                d2[key] = v
                return d2
            return None
        if fname == "row_of":
            return {'on_hand': args[0], 'reserved': args[1], 'reorder_point': args[2]}
        raise NotImplementedError(f"call {fname}")


# --- BDD tests ---

def test_add_one_lowering():
    """Pure arithmetic lowering matches Python."""
    expr = lower_func("def f(x):\n    y = x + 1\n    return y\n")
    interp = SnInterp()
    assert interp.eval(expr, {'x': 5}) == 6


def test_comparison_lowering():
    """Comparison lowering matches Python."""
    expr = lower_func("def f(x):\n    if x < 0:\n"
                        "        return 0 - x\n    return x\n")
    interp = SnInterp()
    assert interp.eval(expr, {'x': -5}) == 5
    assert interp.eval(expr, {'x': 3}) == 3


def test_restock_lowering_produces_expected_shape():
    """The restock lowering produces the expected SnakeletExn structure."""
    src = (
        'def restock(sku, quantity):\n'
        '    row = conn.execute(text("SELECT on_hand, reserved, reorder_point FROM products WHERE sku = ?"), (sku,)).fetchone()\n'
        '    if row is None:\n'
        '        raise ProductNotFoundError(sku, "", quantity, "not found")\n'
        '    conn.execute(text("UPDATE products SET on_hand = on_hand + ? WHERE sku = ?"), (quantity, sku))\n'
        '    return (sku, quantity)\n'
    )
    expr = lower_func(src)
    coq = emit_snakelet(expr)
    assert 'Load' in coq
    assert 'dict_lookup_str' in coq
    assert 'dict_insert_str' in coq
    assert 'Store' in coq
    assert 'Raise' in coq
    assert 'ProductNotFoundError' in coq
    # Should NOT have BinOp inside Call args (hoisted)
    assert '_row_arg_0' in coq


def test_restock_lowering_executes_success_path():
    """Execute the lowered restock program against a concrete initial state."""
    src = (
        'def restock(sku, quantity):\n'
        '    row = conn.execute(text("SELECT on_hand, reserved, reorder_point FROM products WHERE sku = ?"), (sku,)).fetchone()\n'
        '    if row is None:\n'
        '        raise ProductNotFoundError(sku, "", quantity, "not found")\n'
        '    conn.execute(text("UPDATE products SET on_hand = on_hand + ? WHERE sku = ?"), (quantity, sku))\n'
        '    return (sku, quantity)\n'
    )
    expr = lower_func(src)
    interp = SnInterp()
    # Set up the heap: store_loc = 1, contains the products dict
    interp.heap[1] = {'SKU1': {'on_hand': 10, 'reserved': 3, 'reorder_point': 5}}
    # The lowered program uses Var "store_loc" for the heap cell
    # We need to bind store_loc in the environment
    env = {'sku': 'SKU1', 'quantity': 20, 'store_loc': ('loc', 1)}
    result = interp.eval(expr, env)
    # Should return the receipt as a record (dict with string keys)
    assert result == {'0': 'SKU1', '1': 20}
    # The heap should have been updated
    assert interp.heap[1]['SKU1']['on_hand'] == 30  # 10 + 20
    assert interp.heap[1]['SKU1']['reserved'] == 3  # unchanged


def test_restock_lowering_executes_exception_path():
    """Execute the lowered restock program with a missing SKU."""
    src = (
        'def restock(sku, quantity):\n'
        '    row = conn.execute(text("SELECT on_hand, reserved, reorder_point FROM products WHERE sku = ?"), (sku,)).fetchone()\n'
        '    if row is None:\n'
        '        raise ProductNotFoundError(sku, "", quantity, "not found")\n'
        '    conn.execute(text("UPDATE products SET on_hand = on_hand + ? WHERE sku = ?"), (quantity, sku))\n'
        '    return (sku, quantity)\n'
    )
    expr = lower_func(src)
    interp = SnInterp()
    interp.heap[1] = {'SKU1': {'on_hand': 10, 'reserved': 3, 'reorder_point': 5}}
    env = {'sku': 'MISSING', 'quantity': 20, 'store_loc': ('loc', 1)}
    with pytest.raises(Exception) as exc_info:
        interp.eval(expr, env)
    # The exception should be ProductNotFoundError
    assert 'ProductNotFoundError' in str(exc_info.value)
