from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import select

from guitar_searcher.db.seed import load_seed_shops, upsert_shops
from guitar_searcher.db.session import get_session, init_db
from guitar_searcher.models.shop import ShopRow

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
