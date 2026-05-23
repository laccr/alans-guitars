from __future__ import annotations

import asyncio

import typer
from rich.console import Console
from rich.table import Table

from guitar_searcher.db.session import get_session, init_db
from guitar_searcher.schemas import QuerySpec
from guitar_searcher.watch_runner import (
    VALID_CADENCES,
    add_watch,
    list_watches,
    remove_watch,
    run_watch_async,
    set_watch_active,
)

console = Console()
watch_app = typer.Typer(help="Manage saved watches.", no_args_is_help=True)


@watch_app.command("add")
def add(
    name: str = typer.Option(..., "--name", help="Short label for the watch"),
    cadence: str = typer.Option("daily", "--cadence", help="hourly | daily | weekly"),
    brand: str | None = typer.Option(None, "--brand"),
    model: str | None = typer.Option(None, "--model"),
    year_min: int | None = typer.Option(None, "--year-min"),
    year_max: int | None = typer.Option(None, "--year-max"),
    finish: str | None = typer.Option(None, "--finish"),
    max_price: float | None = typer.Option(None, "--max-price"),
    min_price: float | None = typer.Option(None, "--min-price"),
    must_have: list[str] = typer.Option([], "--must-have"),
    exclude: list[str] = typer.Option([], "--exclude"),
    keyword: list[str] = typer.Option([], "--keyword"),
    condition: list[str] = typer.Option([], "--condition"),
    all_original_only: bool = typer.Option(False, "--all-original-only"),
) -> None:
    """Create a new saved watch."""
    if cadence not in VALID_CADENCES:
        raise typer.BadParameter(f"cadence must be one of {sorted(VALID_CADENCES)}")
    query = QuerySpec(
        brand=brand,
        model=model,
        year_min=year_min,
        year_max=year_max,
        finish=finish,
        max_price_usd=max_price,
        min_price_usd=min_price,
        must_have=must_have,
        exclude=exclude,
        keywords=keyword,
        conditions=condition,
        all_original_only=all_original_only,
    )
    init_db()
    with get_session() as session:
        row = add_watch(session, name=name, query=query, cadence=cadence)
        watch_id = row.id
    console.print(f"[green]Added watch #{watch_id}[/green] {name} - {query.display()} ({cadence})")


@watch_app.command("list")
def list_cmd(only_active: bool = typer.Option(False, "--active")) -> None:
    init_db()
    with get_session() as session:
        rows = list_watches(session, only_active=only_active)
    table = Table()
    table.add_column("ID", width=4)
    table.add_column("Name")
    table.add_column("Query")
    table.add_column("Cadence")
    table.add_column("Active", width=6)
    for r in rows:
        q = QuerySpec.model_validate(r.query_spec_json)
        table.add_row(
            str(r.id),
            r.name or "—",
            q.display(),
            r.watch_cadence or "—",
            "yes" if r.watch_active else "no",
        )
    console.print(table)
    console.print(f"[dim]{len(rows)} watches.[/dim]")


@watch_app.command("enable")
def enable(watch_id: int = typer.Argument(...)) -> None:
    init_db()
    with get_session() as session:
        row = set_watch_active(session, watch_id, True)
    console.print(f"[green]Enabled[/green] watch #{row.id} {row.name or ''}")


@watch_app.command("disable")
def disable(watch_id: int = typer.Argument(...)) -> None:
    init_db()
    with get_session() as session:
        row = set_watch_active(session, watch_id, False)
    console.print(f"[yellow]Disabled[/yellow] watch #{row.id} {row.name or ''}")


@watch_app.command("remove")
def remove(watch_id: int = typer.Argument(...)) -> None:
    init_db()
    with get_session() as session:
        remove_watch(session, watch_id)
    console.print(f"[red]Removed[/red] watch #{watch_id}")


@watch_app.command("run")
def run_one(
    watch_id: int = typer.Argument(...),
    notify: bool = typer.Option(True, "--notify/--no-notify"),
    no_llm: bool = typer.Option(False, "--no-llm"),
) -> None:
    """Run a single watch immediately."""
    init_db()
    with get_session() as session:
        from guitar_searcher.models.listing import SearchRow

        watch = session.get(SearchRow, watch_id)
        if watch is None or not watch.is_watch:
            raise typer.BadParameter(f"No watch with id={watch_id}")
        all_matches, new_matches = asyncio.run(
            run_watch_async(session, watch, notify=notify, use_llm_tiebreaker=not no_llm)
        )
    console.print(
        f"watch #{watch_id}: {len(all_matches)} total matches, "
        f"{len(new_matches)} new (notified={notify and bool(new_matches)})"
    )


@watch_app.command("run-all")
def run_all(
    notify: bool = typer.Option(True, "--notify/--no-notify"),
    no_llm: bool = typer.Option(False, "--no-llm"),
) -> None:
    """Run every active watch sequentially."""
    init_db()
    with get_session() as session:
        watches = list_watches(session, only_active=True)
    console.print(f"[bold]Running {len(watches)} active watches...[/bold]")
    for w in watches:
        with get_session() as session:
            row = session.get(type(w), w.id)
            assert row is not None
            all_matches, new_matches = asyncio.run(
                run_watch_async(session, row, notify=notify, use_llm_tiebreaker=not no_llm)
            )
        console.print(
            f"  #{w.id} {w.name}: {len(all_matches)} total, {len(new_matches)} new"
        )


@watch_app.command("schedule")
def schedule() -> None:
    """Run the long-lived APScheduler daemon — re-runs active watches on their cadence."""
    from guitar_searcher.scheduler import run_forever

    run_forever()
