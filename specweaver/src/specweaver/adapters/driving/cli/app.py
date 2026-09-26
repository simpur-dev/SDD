from __future__ import annotations

import asyncio

import typer
from rich.console import Console

from .... import __version__
from ....shared import di
from ....shared.config import Settings

app = typer.Typer(help="SpecWeaver (规格织网) SDD engineering context tool")
console = Console()


@app.command()
def doctor() -> None:
    """Check the full assembly: seekdb, PowerContext and inference mode."""
    settings = Settings()

    async def _run() -> dict:
        async with di.run(settings) as sw:
            return await sw.doctor()

    report = asyncio.run(_run())
    all_ok = True
    for name in ("seekdb", "powercontext"):
        info = report.get(name, {})
        if info.get("ok"):
            console.print(f"[green]OK  [/green] {name}: {info}")
        else:
            all_ok = False
            console.print(f"[red]FAIL[/red] {name}: {info}")
    warning = report.get("bootstrap_errors", {}).get("inference")
    provider = report.get("inference", {}).get("provider")
    if provider == "none" or warning:
        suffix = f" ({warning})" if warning else ""
        console.print(
            f"[yellow]WARN[/yellow] inference not configured "
            f"-> rule (Basic) mode{suffix}"
        )
    else:
        console.print(f"[green]OK  [/green] inference: {provider}")
    raise typer.Exit(0 if all_ok else 1)


@app.command()
def version() -> None:
    console.print(__version__)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
