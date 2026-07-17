"""Gherkin-to-Contract traceability.

Show the complete picture: for each entry point, the Gherkin scenario
block and the fully conjoined contract formula side by side.
"""

from __future__ import annotations

import io as _io
import re
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from gherkin.parser import Parser as _GherkinParser
from rich.console import Console

from specsaver.registry import ContractRecord, get_registry
from specsaver.render import render_contract_from_object, render_entry_point


def _render_contract_for_feature(feat: str, feature_to_contract: dict) -> str:
    """Render the contract for a feature — prefer Contract objects."""
    if feat in feature_to_contract:
        return render_contract_from_object(feature_to_contract[feat])
    return render_entry_point(feat)

# ---------------------------------------------------------------------------
# Console capture (avoids double-output in headless contexts)
# ---------------------------------------------------------------------------


def _capture(build: Callable[[Console], None]) -> str:
    buf = _io.StringIO()
    c = Console(file=buf, width=120, force_terminal=True, color_system="standard")
    build(c)
    return buf.getvalue()


@dataclass
class OutlineInfo:
    name: str
    feature: str
    module: str = ""
    steps: list[str] = field(default_factory=list)
    step_keywords: list[str] = field(default_factory=list)
    examples_count: int = 0


# ---------------------------------------------------------------------------
# Feature-file discovery
# ---------------------------------------------------------------------------


def _find_feature_file(feature_name: str, example_module: str) -> Path | None:
    import importlib
    import os

    parts = example_module.split(".")
    if not parts:
        return None
    mod = importlib.import_module(parts[0])
    pkg_dir = Path(os.path.dirname(mod.__file__ or "")) if mod.__file__ else None
    if pkg_dir is None:
        return None
    for root, _dirs, files in os.walk(str(pkg_dir)):
        for f in files:
            if f == feature_name:
                return Path(root) / f
    return None


def _loaded_features() -> list[tuple[str, str, Path]]:
    registry = get_registry()
    seen: set[tuple[str, str]] = set()
    results: list[tuple[str, str, Path]] = []
    for r in registry.list_all():
        if not r.feature:
            continue
        key = (r.module, r.feature)
        if key in seen:
            continue
        seen.add(key)
        path = _find_feature_file(r.feature, r.module)
        if path:
            results.append((r.module, r.feature, path))
    return results


def _parse_scenario_outlines(feature_text: str) -> list[OutlineInfo]:
    doc = _GherkinParser().parse(feature_text)
    outlines: list[OutlineInfo] = []

    def walk(node):
        if isinstance(node, dict):
            kw = node.get("keyword", "").strip()
            if kw in ("Scenario Outline", "Scenario Template"):
                steps: list[str] = []
                keywords: list[str] = []
                for s in node.get("steps", []):
                    steps.append(s["text"])
                    keywords.append(s.get("keyword", "").strip())
                ex_count = len(node.get("examples", []))
                outlines.append(
                    OutlineInfo(
                        name=node.get("name", ""),
                        feature="",
                        steps=steps,
                        step_keywords=keywords,
                        examples_count=ex_count,
                    )
                )
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(doc.get("feature", {}))
    return outlines


def _all_outlines() -> list[OutlineInfo]:
    result: list[OutlineInfo] = []
    for mod, name, path in _loaded_features():
        outlines = _parse_scenario_outlines(path.read_text())
        for o in outlines:
            o.feature = name
            o.module = mod
        result.extend(outlines)
    return result


def _print_examples_tables(io, outline) -> None:
    """Render each named Examples table for an outline, boxed in a Panel."""
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    from specsaver.gherkin import parse_examples_tables_file

    feature_path = _find_feature_file(outline.feature, outline.module)
    if feature_path is None:
        return
    all_tables = parse_examples_tables_file(feature_path)
    matching = [t for t in all_tables if t.outline_name == outline.name]
    if not matching:
        return

    for t in matching:
        columns = list(t.columns)
        tbl = Table(show_header=True, show_edge=False)
        for col in columns:
            tbl.add_column(col, style="dim")
        for row in t.rows:
            tbl.add_row(*[row[c] for c in columns])
        io.print(
            Panel(
                tbl,
                title=Text(f"Examples: {t.table_name}", style="dim"),
            )
        )


def _row_label(row: dict[str, str]) -> str:
    """Compact row identifier from Gherkin examples values."""
    parts = [f"{k}={v}" for k, v in row.items()]
    return ", ".join(parts[:6])


def _outline_expects_rejection(outline) -> bool:
    """Return True if any Then step mentions 'rejected'."""
    for kw, text in zip(outline.step_keywords, outline.steps, strict=True):
        if kw == "Then" and "rejected" in text.lower():
            return True
    return False


def _check_icon(passed: bool, expects_rejection: bool) -> str:
    """Return a colored icon for a contract check.

    When rejection is expected, a failed precondition is correct
    (shown dim, not red).
    """
    if passed:
        return "[green]✓[/]"
    if expects_rejection:
        return "[dim]✗[/]"
    return "[red]✗[/]"


def _discover_runners() -> dict[str, dict]:
    """Deprecated — use _discover_verify_runners instead."""
    return {}


def _print_verify_results(io, outline, entry_point, builder) -> None:
    """Deprecated — use _print_verify_results_symmetric instead."""
    pass


def _print_verify_results_symmetric(
    io, outline, feature, runner_fn, pre_only=False
) -> None:
    """Run the symmetric runner against every Examples row and report."""
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    from specsaver.gherkin import examples_for, parse_examples_tables_file

    feature_path = _find_feature_file(outline.feature, outline.module)
    if feature_path is None:
        return
    tables = parse_examples_tables_file(feature_path)
    rows = examples_for(tables, outline.name)

    if not rows:
        return

    verdicts: list[tuple[str, str]] = []
    all_ok = True
    for row in rows:
        label = _row_label(row)
        try:
            passed, message = runner_fn(row, pre_only=pre_only)
        except Exception as exc:
            passed, message = False, f"error: {exc}"
        if not passed:
            all_ok = False
        color = "green" if passed else "red"
        verdicts.append((label, f"[{color}]{message}[/]"))

    title = f"Verify: {outline.name}"
    if pre_only:
        title += " (preconditions only)"
    title_style = "bold green" if all_ok else "bold red"
    tbl = Table(show_header=True)
    tbl.add_column("Row", style="dim")
    tbl.add_column("Result")
    for lbl, note in verdicts:
        tbl.add_row(lbl, note)
    io.print(
        Panel(
            tbl,
            title=Text(title, style=title_style),
        )
    )


def _discover_verify_runners() -> dict[str, Callable]:
    """Discover ``__verify_runner__`` dicts from registered modules.

    Returns ``{feature: runner_fn}`` where each runner_fn takes a
    Gherkin Examples row dict and returns ``(passed: bool, message: str)``.

    Checks both the contract module and its parent package, since
    ``__verify_runner__`` is typically defined in the package __init__.
    """
    import importlib

    runners: dict[str, Callable] = {}
    modules_seen: set[str] = set()
    for r in get_registry().list_all():
        candidates = [r.module]
        # Also check parent package (e.g. examples.bank_transfer
        # when contracts are in examples.bank_transfer.contracts)
        parts = r.module.rsplit(".", 1)
        if len(parts) == 2:
            candidates.append(parts[0])
        for mod_name in candidates:
            if mod_name in modules_seen:
                continue
            modules_seen.add(mod_name)
            try:
                mod = importlib.import_module(mod_name)
                mod_runners = getattr(mod, "__verify_runner__", None)
                if isinstance(mod_runners, dict):
                    for feat, fn in mod_runners.items():
                        runners[feat] = fn
            except Exception:
                pass
    return runners


def trace_contract(
    filter_pattern: str | None = None,
    *,
    contracts: list | None = None,
    verify: bool = False,
    pre_only: bool = False,
) -> str:
    """For each feature: the Gherkin scenario block and the full contract.

    When verify=True, runs each Examples row through the symmetric
    runner.  When pre_only=True (implies verify=True), only checks
    admissibility + invariants — no implementation needed.

    When ``contracts`` is provided (a list of ``Contract`` objects),
    those are used directly instead of the flat registry.
    """
    from rich.markup import escape
    from rich.panel import Panel
    from rich.text import Text

    from specsaver.contract_model import Contract

    if pre_only:
        verify = True

    if contracts:
        feature_to_contract: dict[str, Contract] = {
            c.feature: c for c in contracts
        }
        feature_to_step_texts: dict[str, set[str]] = defaultdict(set)
        for c in contracts:
            if c.feature and c.when:
                feature_to_step_texts[c.feature].add(c.when)
    else:
        feature_to_step_texts = defaultdict(set)
        for r in get_registry().list_all():
            if r.feature and r.from_gherkin:
                feature_to_step_texts[r.feature].add(r.from_gherkin)
        feature_to_contract = {}

    outlines = _all_outlines()
    pattern = (
        re.compile(re.escape(filter_pattern), re.IGNORECASE) if filter_pattern else None
    )

    def build(io):
        verify_runners = _discover_verify_runners() if verify else {}
        shown_features: set[str] = set()
        for o in outlines:
            if pattern and not (
                pattern.search(o.name) or any(pattern.search(s) for s in o.steps)
            ):
                continue
            matching_features: set[str] = set()
            for feat, step_texts in feature_to_step_texts.items():
                for st in step_texts:
                    if st in o.steps:
                        matching_features.add(feat)
            if not matching_features:
                continue
            gherkin_body = ""
            last_color = ""
            for kw, text in zip(o.step_keywords, o.steps, strict=True):
                base_colors = {"Given": "green", "When": "yellow", "Then": "cyan"}
                if kw in base_colors:
                    last_color = base_colors[kw]
                color = base_colors.get(kw, last_color or "dim")
                gherkin_body += f"[{color}]{kw:6s}[/] {escape(text)}\n"
            gherkin_body = gherkin_body.rstrip()
            io.print(
                Panel(
                    Text.from_markup(gherkin_body),
                    title=Text(f"Gherkin: {o.name}", style="bold cyan"),
                    subtitle=Text(o.feature, style="dim"),
                )
            )
            _print_examples_tables(io, o)
            for feat in sorted(matching_features):
                shown_features.add(feat)
                if verify and feat in verify_runners:
                    _print_verify_results_symmetric(
                        io, o, feat, verify_runners[feat], pre_only=pre_only
                    )
                io.print(
                    Panel(
                        Text.from_markup(
                            _render_contract_for_feature(feat, feature_to_contract)
                        ),
                        title=Text(f"Contract: [{feat}]", style="bold yellow"),
                    )
                )
            io.print()
        remaining = set(feature_to_step_texts) - shown_features
        if remaining:
            io.print(
                Text("Features without a linked Gherkin scenario:", style="dim")
            )
            for feat in sorted(remaining):
                io.print(f"  [yellow]{feat}[/]")

    return _capture(build)


def trace_steps(
    filter_pattern: str | None = None,
) -> str:
    """Group every contract by its from_gherkin origin step text."""
    from rich.table import Table
    from rich.text import Text

    step_to_contracts: dict[str, list[ContractRecord]] = defaultdict(list)
    for r in get_registry().list_all():
        if r.from_gherkin:
            step_to_contracts[r.from_gherkin].append(r)

    if filter_pattern:
        pat = filter_pattern.lower()
        step_to_contracts = {
            k: v
            for k, v in step_to_contracts.items()
            if pat in k.lower() or any(pat in r.identifier.lower() for r in v)
        }

    if not step_to_contracts:
        return "No traces found." + (
            f" (filter: '{filter_pattern}')" if filter_pattern else ""
        )

    title = "Step → Contract Traces"
    if filter_pattern:
        title += f"  [dim](filter: '{filter_pattern}')[/]"

    def build(io):
        io.print(Text(title, style="bold"))
        io.print()
        for step_text, records in step_to_contracts.items():
            tbl = Table(
                title=Text(step_text, style="bold cyan"),
                show_header=True,
                header_style="bold",
            )
            tbl.add_column("Kind", style="dim")
            tbl.add_column("Contract", style="green")
            tbl.add_column("Entry point", style="yellow")
            tbl.add_column("Feature", style="dim")
            for r in records:
                tbl.add_row(
                    r.kind.name.lower(),
                    r.identifier,
                    r.entry_point or "—",
                    r.feature or "—",
                )
            io.print(tbl)
            io.print()
        total = sum(len(v) for v in step_to_contracts.values())
        io.print(
            f"[dim]{total} contract(s) across {len(step_to_contracts)} "
            f"Gherkin step(s)[/]"
        )

    return _capture(build)


def trace_scenarios(
    filter_pattern: str | None = None,
) -> str:
    """List Scenario Outlines with abstract step templates."""
    from rich.markup import escape
    from rich.panel import Panel
    from rich.text import Text

    outlines = _all_outlines()
    pattern = (
        re.compile(re.escape(filter_pattern), re.IGNORECASE) if filter_pattern else None
    )
    if pattern:
        outlines = [
            o
            for o in outlines
            if pattern.search(o.name) or any(pattern.search(s) for s in o.steps)
        ]

    if not outlines:
        return "No outlines found." + (
            f" (filter: '{filter_pattern}')" if filter_pattern else ""
        )

    title = "Scenario Outlines"
    if filter_pattern:
        title += f"  [dim](filter: '{filter_pattern}')[/]"

    def build(io):
        io.print(Text(title, style="bold"))
        io.print()
        for o in outlines:
            body = "\n".join(f"  • {escape(step)}" for step in o.steps)
            io.print(
                Panel(
                    body,
                    title=Text(o.name, style="bold cyan"),
                    subtitle=Text(o.feature, style="dim"),
                )
            )
            io.print()
        io.print(f"[dim]{len(outlines)} outline(s)[/]")

    return _capture(build)
