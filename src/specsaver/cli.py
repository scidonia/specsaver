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
def list_contracts() -> None:
    """List all registered contracts."""
    from specsaver import get_registry

    registry = get_registry()
    records = registry.list_all()

    if not records:
        typer.echo("No contracts registered.")
        return

    for r in records:
        typer.echo(f"  [{r.category}] {r.identifier}  ({r.status.name})")


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

    from specsaver.render import render_all

    typer.echo(render_all())


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
        help="Run tests for each entry point and show pass/fail inline",
    ),
) -> None:
    """Trace Gherkin scenarios to their contracts, and vice versa."""
    try:
        _import_module(module)
    except ImportError as e:
        typer.echo(f"Error importing {module}: {e}", err=True)
        raise typer.Exit(1) from e

    from specsaver.trace import trace_contract, trace_scenarios, trace_steps

    if mode == "steps":
        output = trace_steps(search)
    elif mode == "scenarios":
        output = trace_scenarios(search)
    else:
        output = trace_contract(search, verify=verify)
    typer.echo(output)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
