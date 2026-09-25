from __future__ import annotations

import asyncio

import typer
from rich.console import Console

from .... import __version__
from ....shared.config import Settings
from ...driven.powercontext.health import check_powercontext
from ...driven.seekdb.health import check_seekdb

app = typer.Typer(help="SpecWeaver (规格织网) SDD engineering context tool")
console = Console()


@app.command()
def doctor() -> None:
    """Check seekdb / PowerContext connectivity and inference configuration."""
    settings = Settings()

    async def _run() -> bool:
        all_ok = True
        for name, coro in (
            ("seekdb", check_seekdb(settings.seekdb)),
            ("powercontext", check_powercontext(settings.powercontext)),
        ):
            try:
                info = await coro
                console.print(f"[green]OK  [/green] {name}: {info}")
            except Exception as exc:  # noqa: BLE001
                all_ok = False
                console.print(f"[red]FAIL[/red] {name}: {exc}")
        if settings.inference.provider == "none" or not settings.inference.api_key:
            console.print(
                "[yellow]WARN[/yellow] inference not configured -> rule (Basic) mode"
            )
        return all_ok

    ok = asyncio.run(_run())
    raise typer.Exit(0 if ok else 1)


@app.command()
def version() -> None:
    console.print(__version__)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
