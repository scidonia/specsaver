"""CLI entry point for specsaver."""

import typer

app = typer.Typer(help="specsaver — specification-driven verification")


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
    import importlib

    try:
        importlib.import_module(module)
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


def main() -> None:
    app()


if __name__ == "__main__":
    main()
