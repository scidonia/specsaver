"""Semantic frame conditions — make ``writes`` enforceable.

A contract's ``writes`` set declares the *footprint*: the observed-state
locations an operation may change.  This module interprets that set at
runtime, so every "X is unchanged" clause that follows from the frame is
generated rather than hand-written.

Path language (three shapes):

    state.reservation_log            bare field      — whole field may change
    state.products[sku]              keyed row       — one map entry may change
    state.products[sku].reserved     keyed attribute — one attribute of one
                                     map entry may change

``[sku]`` resolves against the call arguments (``args.sku``).

Frame semantics, given ``(schema, writes, before, args, after)``:

  - Fields covered by a bare path are unconstrained (ensures pin content).
  - Fields covered only by keyed paths must keep their key set; every
    attribute not covered by a keyed-attribute path must be equal.
  - Every other observed field in the schema must be value-equal.

Also provides :func:`check_derived`: derived fields are not framed (they
follow from observed), but they must agree with the contract's
``derives`` — closing the drift hole between projection and contract.
"""

from __future__ import annotations

import ast
import dataclasses
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WritePath:
    field: str
    key: str | None    # args attribute name, if the path is keyed
    attr: str | None   # row attribute, if the path goes that deep


def parse_write_path(raw: str) -> WritePath:
    """Parse a write path via the Python AST — no regex munging.

    ``state.reservation_log`` → bare field; ``state.products[sku]`` →
    keyed row; ``state.products[sku].reserved`` → keyed attribute.
    The key must be a plain name (resolved against the call args).
    """
    try:
        tree = ast.parse(raw, mode="eval").body
    except SyntaxError as exc:
        raise ValueError(f"malformed write path: {raw!r}") from exc

    def _state_attr(node: ast.expr) -> str | None:
        if (isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "state"):
            return node.attr
        return None

    def _key_of(node: ast.expr) -> str | None:
        if (isinstance(node, ast.Subscript)
                and isinstance(node.slice, ast.Name)):
            return node.slice.id
        return None

    # Bare field: state.<field>
    if isinstance(tree, ast.Attribute) and isinstance(tree.value, ast.Name):
        field = _state_attr(tree)
        if field is not None:
            return WritePath(field=field, key=None, attr=None)
    # Keyed attribute: state.<field>[<key>].<attr>
    if (isinstance(tree, ast.Attribute)
            and isinstance(tree.value, ast.Subscript)):
        key = _key_of(tree.value)
        field = _state_attr(tree.value.value)
        if key is not None and field is not None:
            return WritePath(field=field, key=key, attr=tree.attr)
    # Keyed row: state.<field>[<key>]
    if isinstance(tree, ast.Subscript):
        key = _key_of(tree)
        field = _state_attr(tree.value)
        if key is not None and field is not None:
            return WritePath(field=field, key=key, attr=None)
    raise ValueError(f"malformed write path: {raw!r}")


def _resolve_key(args: Any, key_name: str) -> Any:
    return getattr(args, key_name)


def check_frame(
    state_schema: dict[str, Any],
    writes: set[str],
    before: Any,
    args: Any,
    after: Any,
) -> list[str]:
    """Check that nothing outside *writes* changed between the snapshots.

    *before* / *after* are SpecState values with an ``observed`` attribute;
    *state_schema* maps field names to StateField (provenance "observed"
    selects the framed universe).  Returns a list of violation messages —
    empty means the frame held.
    """
    paths = [parse_write_path(w) for w in writes]
    bare_fields = {p.field for p in paths if p.key is None and p.attr is None}
    keyed: dict[str, list[WritePath]] = {}
    for p in paths:
        if p.field not in bare_fields:
            keyed.setdefault(p.field, []).append(p)

    violations: list[str] = []
    for name, sf in state_schema.items():
        if sf.provenance != "observed":
            continue
        old_val = getattr(before.observed, name, None)
        new_val = getattr(after.observed, name, None)

        if name in bare_fields:
            continue

        if name in keyed:
            violations.extend(
                _check_keyed_field(name, keyed[name], old_val, new_val, args)
            )
            continue

        if new_val != old_val:
            violations.append(f"state.{name} changed outside the frame")

    return violations


def _check_keyed_field(
    name: str,
    paths: list[WritePath],
    old_map: Any,
    new_map: Any,
    args: Any,
) -> list[str]:
    whole_keys = {
        _resolve_key(args, p.key) for p in paths if p.key and p.attr is None
    }
    written_attrs = {
        (_resolve_key(args, p.key), p.attr)
        for p in paths
        if p.key and p.attr is not None
    }

    violations: list[str] = []
    old_keys = set(old_map)
    new_keys = set(new_map)
    # Key-set discipline: no deletions, ever; additions only via
    # keyed-row write paths (state.<field>[<key>] with no attribute —
    # an insert permission).  Keyed-attribute paths keep the key set
    # stable exactly.
    removed = old_keys - new_keys
    if removed:
        violations.append(
            f"state.{name} keys removed outside the frame: "
            f"{sorted(removed)}"
        )
    illegal_adds = (new_keys - old_keys) - whole_keys
    if illegal_adds:
        violations.append(
            f"state.{name} keys added outside the frame: "
            f"{sorted(illegal_adds)}"
        )
    if removed or illegal_adds:
        return violations

    for k in old_keys:
        if k in whole_keys:
            continue
        old_row = old_map[k]
        new_row = new_map[k]
        attrs = {a for (kk, a) in written_attrs if kk == k}
        if not attrs:
            if new_row != old_row:
                violations.append(
                    f"state.{name}[{k!r}] changed outside the frame"
                )
            continue
        if not dataclasses.is_dataclass(old_row):
            raise TypeError(
                f"state.{name} rows must be dataclasses for "
                f"attribute-level frames, got {type(old_row).__name__}"
            )
        for f in dataclasses.fields(old_row):
            if f.name in attrs:
                continue
            if getattr(new_row, f.name) != getattr(old_row, f.name):
                violations.append(
                    f"state.{name}[{k!r}].{f.name} changed outside the frame"
                )
    return violations


def check_derived(derives: dict[str, Any], after: Any) -> list[str]:
    """Check that derived fields agree with the contract's derivations.

    Derived state is recomputed, never written — but the projection and
    the contract's ``derives`` define it independently, so verify they
    did not drift apart.
    """
    violations: list[str] = []
    for name, fn in derives.items():
        actual = getattr(after.derived, name, None)
        expected = fn(after)
        if actual != expected:
            violations.append(
                f"derived {name}: projection says {actual}, "
                f"contract derives {expected}"
            )
    return violations
