from __future__ import annotations

import asyncio

import typer
from rich.console import Console
from rich.table import Table

from guitar_searcher.db.session import get_session, init_db
from guitar_searcher.matching.score import ScoredListing
from guitar_searcher.schemas import QuerySpec
from guitar_searcher.search_runner import run_search

console = Console()


def search(
    brand: str | None = typer.Option(None, "--brand", help="e.g. Fender, Gibson"),
    model: str | None = typer.Option(None, "--model", help="e.g. Jaguar, Les Paul Standard"),
    year_min: int | None = typer.Option(None, "--year-min"),
    year_max: int | None = typer.Option(None, "--year-max"),
    finish: str | None = typer.Option(None, "--finish", help="e.g. sunburst, candy apple red"),
    condition: list[str] = typer.Option([], "--condition", help="Repeatable: --condition used"),
    max_price: float | None = typer.Option(None, "--max-price"),
    min_price: float | None = typer.Option(None, "--min-price"),
    must_have: list[str] = typer.Option([], "--must-have", help="Repeatable required keyword"),
    exclude: list[str] = typer.Option([], "--exclude", help="Repeatable excluded keyword"),
    keyword: list[str] = typer.Option([], "--keyword", help="Repeatable freeform keyword"),
    all_original_only: bool = typer.Option(False, "--all-original-only"),
    min_score: float = typer.Option(0.35, "--min-score", help="Cutoff for results"),
    no_llm: bool = typer.Option(False, "--no-llm", help="Skip LLM tiebreaker"),
    no_save: bool = typer.Option(False, "--no-save", help="Don't persist results"),
    limit: int = typer.Option(25, "--limit", help="Max rows to print"),
) -> None:
    """Run a single search across all enabled scrapers."""
    query = QuerySpec(
        brand=brand,
        model=model,
        year_min=year_min,
        year_max=year_max,
        finish=finish,
        conditions=condition,
        max_price_usd=max_price,
        min_price_usd=min_price,
        must_have=must_have,
        exclude=exclude,
        keywords=keyword,
        all_original_only=all_original_only,
    )

    init_db()

    with get_session() as session:
        _run, scored = asyncio.run(
            run_search(
                session,
                query,
                save=not no_save,
                use_llm_tiebreaker=not no_llm,
                min_score=min_score,
            )
        )
        _print_results(query, scored, limit)


def _print_results(query: QuerySpec, scored: list[ScoredListing], limit: int) -> None:
    console.print()
    console.rule(f"[bold]{query.display()}[/bold]")
    if not scored:
        console.print("[yellow]No matches above threshold.[/yellow]")
        return

    table = Table(show_lines=False, expand=True)
    table.add_column("#", width=3)
    table.add_column("Score", width=6)
    table.add_column("Shop")
    table.add_column("Title", overflow="fold")
    table.add_column("Year", width=8)
    table.add_column("Price", width=10, justify="right")
    table.add_column("URL", overflow="fold")
    table.add_column("Why", overflow="fold")

    for i, s in enumerate(scored[:limit], 1):
        listing = s.listing
        price = f"${listing.price_usd:,.0f}" if listing.price_usd is not None else "—"
        year = (
            f"{listing.year}"
            + (f" ({listing.year_confidence:.0%})" if listing.year and listing.year_confidence < 1 else "")
            if listing.year
            else "—"
        )
        table.add_row(
            str(i),
            f"{s.score:.2f}",
            listing.shop_name,
            listing.raw_title,
            year,
            price,
            str(listing.url),
            s.reasoning,
        )
    console.print(table)
    console.print(f"\n[dim]{len(scored)} total matches; showing {min(limit, len(scored))}.[/dim]")
