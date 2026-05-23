from __future__ import annotations

import asyncio

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import select

from guitar_searcher.db.seed import _to_row, load_seed_shops, upsert_shops
from guitar_searcher.db.session import get_session, init_db
from guitar_searcher.discovery.dedupe import find_existing_shop, merge_into
from guitar_searcher.discovery.osm import discover_osm_shops
from guitar_searcher.discovery.reverb_directory import discover_reverb_shops
from guitar_searcher.models.shop import ShopRow
from guitar_searcher.schemas.shop import Shop

console = Console()
shops_app = typer.Typer(help="Manage the shop directory.", no_args_is_help=True)


@shops_app.command("seed")
def seed() -> None:
    """Load the hand-curated shop seed list into the database."""
    init_db()
    shops = load_seed_shops()
    with get_session() as session:
        inserted, updated = upsert_shops(session, shops)
    console.print(f"[green]Seed loaded.[/green] inserted={inserted} updated={updated}")


@shops_app.command("discover")
def discover(
    source: str = typer.Option(..., "--source", help="reverb | osm"),
    max_shops: int = typer.Option(500, "--max", help="Cap for reverb directory discovery"),
) -> None:
    """Discover new shops from a directory source and merge into the database."""
    init_db()
    if source == "reverb":
        result = asyncio.run(discover_reverb_shops(max_unique_shops=max_shops))
        candidates = result.us_shops
        console.print(
            f"[bold]Reverb directory:[/bold] examined {result.shops_examined} shops, "
            f"{len(candidates)} US-based candidates"
        )
    elif source == "osm":
        try:
            osm_result = asyncio.run(discover_osm_shops())
        except RuntimeError as exc:
            console.print(f"[red]OSM discovery failed:[/red] {exc}")
            raise typer.Exit(code=1) from exc
        candidates = osm_result.candidates
        console.print(
            f"[bold]OSM Overpass:[/bold] {osm_result.raw_elements} elements, "
            f"{len(candidates)} candidates"
        )
    else:
        raise typer.BadParameter("--source must be 'reverb' or 'osm'")

    inserted, merged = _persist_candidates(candidates)
    console.print(f"[green]Done.[/green] inserted={inserted} merged_into_existing={merged}")


def _persist_candidates(candidates: list[Shop]) -> tuple[int, int]:
    inserted = 0
    merged = 0
    with get_session() as session:
        for cand in candidates:
            existing = find_existing_shop(session, cand)
            if existing is None:
                session.add(_to_row(cand))
                inserted += 1
            else:
                merge_into(existing, cand)
                merged += 1
    return inserted, merged


@shops_app.command("add")
def add_shop(
    name: str = typer.Option(..., "--name"),
    domain: str = typer.Option(..., "--domain", help="bare domain, e.g. mygshop.com"),
    email: str | None = typer.Option(None, "--email"),
    website_url: str | None = typer.Option(None, "--website"),
    city: str | None = typer.Option(None, "--city"),
    state: str | None = typer.Option(None, "--state"),
    timezone: str | None = typer.Option(None, "--tz", help="IANA tz, e.g. America/New_York"),
    strategy: str = typer.Option("email_only", "--strategy"),
    classification: str = typer.Option("unknown", "--classification"),
    notes: str | None = typer.Option(None, "--notes"),
    active: bool = typer.Option(True, "--active/--inactive"),
) -> None:
    """Insert one shop manually (e.g. for testing outreach or for shops you've found by hand)."""
    init_db()
    shop = Shop(
        name=name,
        domain=domain,
        website_url=website_url or f"https://{domain}",
        email=email,
        city=city,
        state=state,
        timezone=timezone,
        inventory_strategy=strategy,
        classification=classification,
        notes=notes,
        active=active,
        discovered_from="manual",
    )
    with get_session() as session:
        existing = find_existing_shop(session, shop)
        if existing is not None:
            console.print(f"[yellow]Shop already exists (id={existing.id}, name={existing.name}).[/yellow]")
            return
        session.add(_to_row(shop))
    console.print(f"[green]Added shop[/green] {name} ({domain})")


@shops_app.command("list")
def list_shops(
    only_active: bool = typer.Option(True, "--active/--all"),
) -> None:
    """List shops in the directory."""
    init_db()
    with get_session() as session:
        stmt = select(ShopRow).order_by(ShopRow.name)
        if only_active:
            stmt = stmt.where(ShopRow.active.is_(True))
        rows = session.execute(stmt).scalars().all()

    table = Table(show_lines=False)
    table.add_column("Name")
    table.add_column("Domain")
    table.add_column("Class")
    table.add_column("Strategy")
    table.add_column("Scraper")
    table.add_column("TZ")
    table.add_column("Active", width=6)
    for row in rows:
        table.add_row(
            row.name,
            row.domain,
            row.classification,
            row.inventory_strategy,
            row.scraper_module or "—",
            row.timezone or "—",
            "yes" if row.active else "no",
        )
    console.print(table)
    console.print(f"[dim]{len(rows)} shops.[/dim]")
