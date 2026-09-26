from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import typer
from rich.console import Console

from .... import __version__
from ....application.engines.assembly import render_json
from ....application.usecases.complete_task import CompleteTaskRequest
from ....application.usecases.create_handoff import CreateHandoffRequest
from ....application.usecases.get_context import GetContextRequest
from ....application.usecases.ingest_project import IngestProjectRequest
from ....application.usecases.resume_task import ResumeTaskRequest
from ....shared import di
from ....shared.config import Settings
from ....shared.errors import SWError

app = typer.Typer(help="SpecWeaver (规格织网) SDD engineering context tool")
console = Console()

_JSON = typer.Option(False, "--json", help="Machine-readable JSON output.")
_USAGE = typer.Option(
    "", "--usage-out", help="Write telemetry span records (CSV) to this path."
)
_STATE = typer.Option(
    [], "--state", help="Completed-state claim (repeatable)."
)
_NEXT_STEP = typer.Option(
    [], "--next-step", help="Planned next work (repeatable)."
)
_OMISSION = typer.Option(
    [], "--omission", help="Unverified item (repeatable)."
)


def _execute(
    op: Callable[[di.SpecWeaverApp], Awaitable[Any]], usage_out: str
) -> Any:
    """Run one usecase through the full composition root."""

    async def _main() -> Any:
        async with di.run(Settings()) as sw:
            try:
                try:
                    return await op(sw)
                except SWError as exc:
                    console.print(
                        f"[red]ERROR[/red] [{exc.code}] {exc.message}"
                    )
                    raise typer.Exit(2) from exc
            finally:
                if usage_out:
                    try:
                        sw.telemetry.to_csv(usage_out)
                    except OSError as exc:
                        # audit C6: a broken --usage-out path is a traceable
                        # command failure (exit 3), never a raw traceback
                        console.print(
                            f"[red]ERROR[/red] [SW-ERROR] cannot write "
                            f"--usage-out {usage_out!r}: {exc}"
                        )
                        raise typer.Exit(3) from exc

    return asyncio.run(_main())


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
def ingest(
    project_id: str,
    scope_id: str = typer.Option(
        "", help="PowerContext scope id; resolved from the project when empty."
    ),
    register_source: bool = typer.Option(
        True, help="Also register an ingestion note in memory."
    ),
    as_json: bool = _JSON,
    usage_out: str = _USAGE,
) -> None:
    """Ingest the workspace into the seekdb catalog (incremental)."""

    async def _op(sw: di.SpecWeaverApp) -> Any:
        sid = (
            await sw.ensure_scope(project_id, scope_id)
            if register_source
            else scope_id
        )
        return await sw.usecases["ingest_project"](
            IngestProjectRequest(
                project_id=project_id,
                scope_id=sid,
                register_source=register_source,
            )
        )

    report = _execute(_op, usage_out)
    if as_json:
        console.print_json(data=report.model_dump(mode="json"))
    else:
        console.print(
            f"ingest {report.project_id}: +{report.added} ~{report.updated} "
            f"={report.unchanged} skip={report.skipped} "
            f"relations={report.relations} "
            f"deprecated={report.deprecated} "
            f"dup_ids={report.duplicate_ids or 'none'} "
            f"source_registered={report.source_registered}"
        )


@app.command()
def context(
    project_id: str,
    task_text: str,
    base_ref: str = typer.Option(
        "", help="Git ref the task starts from (freshness baseline)."
    ),
    as_json: bool = _JSON,
    usage_out: str = _USAGE,
) -> None:
    """Assemble the budgeted Context Bundle for a task."""

    async def _op(sw: di.SpecWeaverApp) -> Any:
        return await sw.usecases["get_context"](
            GetContextRequest(
                project_id=project_id,
                task_text=task_text,
                base_ref=base_ref or None,
            )
        )

    result = _execute(_op, usage_out)
    if as_json:
        # raw stdout: rich would wrap long lines and break JSON parsing
        typer.echo(render_json(result.bundle))
    else:
        console.print(result.markdown)


@app.command()
def finish(
    project_id: str,
    task_id: str,
    base_ref: str,
    test_command: str = typer.Option(
        "pytest", help="Test command run through the workspace test runner."
    ),
    scope_id: str = typer.Option("", help="PowerContext scope id."),
    register_outcome: bool = typer.Option(
        True, help="Also record the task outcome in memory."
    ),
    as_json: bool = _JSON,
    usage_out: str = _USAGE,
) -> None:
    """Complete a task: run tests, reconcile artifacts, record evidence.

    Exits 1 when tests fail (change sets are only written on success).
    """

    async def _op(sw: di.SpecWeaverApp) -> Any:
        sid = (
            await sw.ensure_scope(project_id, scope_id)
            if register_outcome
            else scope_id
        )
        return await sw.usecases["complete_task"](
            CompleteTaskRequest(
                project_id=project_id,
                task_id=task_id,
                base_ref=base_ref,
                scope_id=sid,
                test_command=test_command,
                register_outcome=register_outcome,
            )
        )

    report = _execute(_op, usage_out)
    if as_json:
        console.print_json(data=report.model_dump(mode="json"))
    else:
        console.print(
            f"finish {report.task_id}: tests "
            f"{report.test_passed}/{report.test_total} passed, "
            f"{report.test_failed} failed; files_changed="
            f"{report.files_changed} updated={len(report.updated_ids)} "
            f"superseded={len(report.superseded_ids)} "
            f"change_set={report.change_set_id} test_run={report.test_run_id}"
        )
    raise typer.Exit(0 if report.success else 1)


@app.command()
def handoff(
    project_id: str,
    objective: str = typer.Option("", help="Task objective to hand over."),
    state: list[str] = _STATE,
    next_step: list[str] = _NEXT_STEP,
    omission: list[str] = _OMISSION,
    scope_id: str = typer.Option("", help="PowerContext scope id."),
    as_json: bool = _JSON,
    usage_out: str = _USAGE,
) -> None:
    """Commit a handoff snapshot; print the rev for `resume --handoff-rev`."""

    async def _op(sw: di.SpecWeaverApp) -> Any:
        sid = await sw.ensure_scope(project_id, scope_id)
        return await sw.usecases["create_handoff"](
            CreateHandoffRequest(
                project_id=project_id,
                scope_id=sid,
                objective=objective,
                state=list(state),
                next_steps=list(next_step),
                omissions=list(omission),
            )
        )

    report = _execute(_op, usage_out)
    if as_json:
        console.print_json(data=report.model_dump(mode="json"))
    else:
        console.print(
            f"handoff committed: rev={report.handoff_rev} "
            f"scope={report.scope_id} next_steps={len(report.next_steps)} "
            f"unverified={len(report.unverified)}"
        )


@app.command()
def resume(
    project_id: str,
    objective: str = typer.Option(
        "", help="Task objective; taken from the handoff when empty."
    ),
    handoff_rev: str = typer.Option(
        "", help="Handoff revision id to continue from (optional)."
    ),
    scope_id: str = typer.Option("", help="PowerContext scope id."),
    use_handoff: bool = typer.Option(
        True, help="Resume from the PowerContext handoff when given a rev."
    ),
    as_json: bool = _JSON,
    usage_out: str = _USAGE,
) -> None:
    """Resume a task: continue handoff, verify catalog, rebuild context."""

    async def _op(sw: di.SpecWeaverApp) -> Any:
        sid = (
            await sw.ensure_scope(project_id, scope_id)
            if use_handoff and handoff_rev
            else scope_id
        )
        return await sw.usecases["resume_task"](
            ResumeTaskRequest(
                project_id=project_id,
                scope_id=sid,
                objective=objective,
                handoff_rev=handoff_rev,
                use_handoff=use_handoff,
            )
        )

    report = _execute(_op, usage_out)
    if as_json:
        console.print_json(data=report.model_dump(mode="json"))
    else:
        if report.handoff_error:
            console.print(
                f"[yellow]WARN[/yellow] handoff resume failed: "
                f"{report.handoff_error}"
            )
        if report.mismatches:
            console.print(
                f"[yellow]WARN[/yellow] {len(report.mismatches)} catalog/workspace "
                "mismatch(es):"
            )
            for m in report.mismatches:
                console.print(f"  - {m.artifact_id}: {m.issue} ({m.source_uri})")
        else:
            console.print("catalog matches the workspace (0 mismatches)")
        console.print(report.context.markdown)


@app.command()
def version() -> None:
    console.print(__version__)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
