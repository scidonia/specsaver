"""CLI entry point for specsaver."""

from __future__ import annotations

import sys
from pathlib import Path

import typer

app = typer.Typer(help="specsaver — specification-driven verification")


def _import_module(module: str) -> None:
    """Import a module, ensuring the current directory is on sys.path."""
    cwd = str(Path.cwd())
    if cwd not in sys.path:
        sys.path.insert(0, cwd)
    import importlib

    importlib.import_module(module)


@app.command()
def list_contracts(
    module: str = typer.Argument(
        None, help="Dotted module path to load contracts from (optional)"
    ),
) -> None:
    """List all registered contracts."""
    if module:
        try:
            _import_module(module)
        except ImportError as e:
            typer.echo(f"Error importing {module}: {e}", err=True)
            raise typer.Exit(1) from e

    from specsaver import get_registry

    registry = get_registry()
    records = registry.list_all()

    if not records:
        typer.echo("No contracts registered.")
        return

    for r in records:
        typer.echo(f"  [{r.category}] {r.identifier}  ({r.status.name})")
    typer.echo(f"\n  {len(records)} contract(s) total.")


@app.command()
def check(
    module: str = typer.Argument(..., help="Dotted module path to scan for contracts"),
) -> None:
    """Load a module and report its contracts."""
    try:
        _import_module(module)
    except ImportError as e:
        typer.echo(f"Error importing {module}: {e}", err=True)
        raise typer.Exit(1) from e

    from specsaver import get_registry

    registry = get_registry()
    records = registry.list_by_module(module)

    if not records:
        typer.echo(f"No contracts found in {module}.")
        return

    for r in records:
        typer.echo(f"  [{r.category}] {r.name:40s}  ({r.status.name})")
    typer.echo(f"\n  {len(records)} contract(s) total.")


@app.command()
def render(
    module: str = typer.Argument(..., help="Dotted module path to load contracts from"),
) -> None:
    """Load a module and display contracts as conjoined logical formulas."""
    try:
        _import_module(module)
    except ImportError as e:
        typer.echo(f"Error importing {module}: {e}", err=True)
        raise typer.Exit(1) from e

    import sys

    from specsaver.contract_model import Contract
    from specsaver.render import render_contract_from_object

    mod = sys.modules.get(module)
    if mod is None:
        typer.echo("No contracts registered.", err=True)
        raise typer.Exit(1)

    contracts = [
        v for v in vars(mod).values()
        if isinstance(v, Contract)
    ]
    if not contracts:
        typer.echo("No Contract objects found in module.", err=True)
        raise typer.Exit(1)

    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text

    mod = sys.modules.get(module)
    if mod is None:
        typer.echo("No contracts registered.", err=True)
        raise typer.Exit(1)

    contracts = [
        v for v in vars(mod).values()
        if isinstance(v, Contract)
    ]
    if not contracts:
        typer.echo("No Contract objects found in module.", err=True)
        raise typer.Exit(1)

    console = Console()
    from rich.markup import escape
    for c in contracts:
        body = render_contract_from_object(c)
        qualname = getattr(c.impl, "__qualname__", "?")
        modname = getattr(c.impl, "__module__", "?")
        entry = f"{modname}.{qualname}"
        subtitle = f"feature: {c.feature}"
        if c.when:
            subtitle += f"  |  when: {escape(c.when)}"
        console.print(
            Panel.fit(
                Text.from_markup(body),
                title=f"[bold]Contract:[/] {escape(entry)}",
                subtitle=subtitle,
                title_align="left",
                subtitle_align="left",
                border_style="bold",
            )
        )
        console.print()


@app.command()
def trace(
    module: str = typer.Argument(..., help="Dotted module path to load contracts from"),
    search: str | None = typer.Option(
        None, "--search", "-s", help="Filter by scenario, step, or contract name"
    ),
    mode: str = typer.Option(
        "contract",
        "--mode",
        "-m",
        help="Display mode: contract (Gherkin+contract), steps, scenarios",
    ),
    verify: bool = typer.Option(
        False,
        "--verify",
        help="Run tests for each feature and show pass/fail inline",
    ),
    pre_only: bool = typer.Option(
        False,
        "--pre-only",
        help="Check only preconditions + invariants against examples (no impl needed)",
    ),
) -> None:
    """Trace Gherkin scenarios to their contracts, and vice versa."""
    import sys

    from specsaver.contract_model import Contract

    try:
        _import_module(module)
    except ImportError as e:
        typer.echo(f"Error importing {module}: {e}", err=True)
        raise typer.Exit(1) from e

    mod = sys.modules.get(module)
    contracts: list = []
    if mod is not None:
        for v in vars(mod).values():
            if isinstance(v, Contract):
                contracts.append(v)

    from specsaver.trace import trace_contract, trace_scenarios, trace_steps

    if mode == "steps":
        output = trace_steps(search)
    elif mode == "scenarios":
        output = trace_scenarios(search)
    else:
        output = trace_contract(search, contracts=contracts,
                                verify=verify, pre_only=pre_only)
    typer.echo(output)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
