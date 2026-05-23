from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import func, select

from guitar_searcher.db.session import get_session, init_db
from guitar_searcher.models.listing import SearchRow
from guitar_searcher.models.outreach import (
    OptOutRow,
    OutreachAttemptRow,
    OutreachReplyRow,
)
from guitar_searcher.outreach.classifier import classify_pending
from guitar_searcher.outreach.compliance import (
    CanSpamConfig,
    MissingComplianceField,
    ensure_can_spam_ready,
)
from guitar_searcher.outreach.inbox import ImapNotConfigured, poll_replies
from guitar_searcher.outreach.queue import (
    approve_draft,
    create_draft_attempts,
    eligible_outreach_shops,
)
from guitar_searcher.outreach.sender import (
    OutreachSendError,
    send_outreach_attempt,
)
from guitar_searcher.schemas import QuerySpec

console = Console()
outreach_app = typer.Typer(help="Email outreach to shops without parseable inventory.", no_args_is_help=True)


@outreach_app.command("check")
def check() -> None:
    """Verify CAN-SPAM / SMTP / IMAP config without sending anything."""
    init_db()
    issues: list[str] = []
    try:
        cfg: CanSpamConfig | None = ensure_can_spam_ready()
    except MissingComplianceField as exc:
        cfg = None
        issues.append(f"CAN-SPAM: {exc}")

    from guitar_searcher.config import get_settings

    s = get_settings()
    if not all([s.smtp_host, s.smtp_username, s.smtp_password]):
        issues.append("SMTP not configured (GS_SMTP_* fields).")
    if not all([s.imap_host, s.imap_username, s.imap_password]):
        issues.append("IMAP not configured (replies cannot be polled).")

    if cfg:
        console.print("[green]CAN-SPAM ready.[/green]")
        console.print(f"  sender: {cfg.sender_name} <{cfg.reply_to}>")
        console.print(f"  postal: {cfg.physical_address}")
    if issues:
        console.print("\n[yellow]Issues:[/yellow]")
        for i in issues:
            console.print(f"  - {i}")
    else:
        console.print("[green]All systems go. Outreach is ready to draft and send.[/green]")


@outreach_app.command("draft")
def draft(
    search_id: int | None = typer.Option(None, "--search-id", help="Associate drafts with a saved search/watch"),
    brand: str | None = typer.Option(None, "--brand"),
    model: str | None = typer.Option(None, "--model"),
    year_min: int | None = typer.Option(None, "--year-min"),
    year_max: int | None = typer.Option(None, "--year-max"),
    finish: str | None = typer.Option(None, "--finish"),
    max_price: float | None = typer.Option(None, "--max-price"),
    no_llm: bool = typer.Option(False, "--no-llm"),
    limit: int = typer.Option(0, "--limit", help="Cap number of drafts (0 = no limit)"),
) -> None:
    """Generate draft inquiry emails for shops eligible for outreach."""
    init_db()
    try:
        ensure_can_spam_ready()
    except MissingComplianceField as exc:
        console.print(f"[red]Cannot draft:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    if search_id:
        with get_session() as session:
            search = session.get(SearchRow, search_id)
            if search is None:
                raise typer.BadParameter(f"No search/watch with id={search_id}")
            query = QuerySpec.model_validate(search.query_spec_json)
    else:
        query = QuerySpec(
            brand=brand,
            model=model,
            year_min=year_min,
            year_max=year_max,
            finish=finish,
            max_price_usd=max_price,
        )

    with get_session() as session:
        shops = eligible_outreach_shops(session)
        if limit > 0:
            shops = shops[:limit]
        if not shops:
            console.print("[yellow]No eligible shops for outreach.[/yellow]")
            return
        drafts = create_draft_attempts(
            session,
            search_id=search_id,
            query=query,
            shops=shops,
            use_llm_personalization=not no_llm,
        )
        draft_ids = [d.id for d in drafts]
    console.print(f"[green]Drafted {len(draft_ids)} inquiries.[/green]")
    console.print("Review with: [bold]guitar-searcher outreach review[/bold]")
    console.print(
        "Approve all with: [bold]guitar-searcher outreach approve --all[/bold]"
    )


@outreach_app.command("review")
def review(
    status: str = typer.Option("draft", "--status", help="draft | queued | sent | replied | failed | suppressed"),
    limit: int = typer.Option(20, "--limit"),
) -> None:
    """List outreach attempts by status."""
    init_db()
    with get_session() as session:
        rows = (
            session.execute(
                select(OutreachAttemptRow)
                .where(OutreachAttemptRow.status == status)
                .order_by(OutreachAttemptRow.id.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
    if not rows:
        console.print(f"[yellow]No attempts with status={status}.[/yellow]")
        return
    table = Table()
    table.add_column("ID", width=5)
    table.add_column("Shop")
    table.add_column("To")
    table.add_column("Subject")
    table.add_column("Sent")
    for r in rows:
        table.add_row(
            str(r.id),
            r.shop.name if r.shop else f"#{r.shop_id}",
            r.to_addr,
            r.subject,
            r.sent_at.strftime("%Y-%m-%d %H:%M") if r.sent_at else "—",
        )
    console.print(table)
    console.print(f"[dim]{len(rows)} of status={status}[/dim]")


@outreach_app.command("show")
def show(attempt_id: int = typer.Argument(...)) -> None:
    """Print the full body of one outreach attempt."""
    init_db()
    with get_session() as session:
        row = session.get(OutreachAttemptRow, attempt_id)
        if row is None:
            raise typer.BadParameter(f"No attempt {attempt_id}")
        body = row.message_body
        to = row.to_addr
        subj = row.subject
        shop_name = row.shop.name if row.shop else f"#{row.shop_id}"
        status = row.status
    console.rule(f"attempt #{attempt_id}  [{status}]")
    console.print(f"to: {to} ({shop_name})")
    console.print(f"subject: {subj}")
    console.rule("body")
    console.print(body)


@outreach_app.command("approve")
def approve(
    attempt_id: int | None = typer.Argument(None),
    approve_all: bool = typer.Option(False, "--all", help="Approve every draft"),
) -> None:
    """Approve a single draft by id, or all current drafts with --all."""
    init_db()
    with get_session() as session:
        if approve_all:
            ids = [
                r.id
                for r in session.execute(
                    select(OutreachAttemptRow).where(OutreachAttemptRow.status == "draft")
                )
                .scalars()
                .all()
            ]
        elif attempt_id is not None:
            ids = [attempt_id]
        else:
            raise typer.BadParameter("Pass an attempt id or --all")
        for aid in ids:
            approve_draft(session, aid)
    console.print(f"[green]Approved {len(ids)} attempt(s).[/green]")


@outreach_app.command("send")
def send(
    dry_run: bool = typer.Option(False, "--dry-run", help="Don't actually send; mark dry_run"),
    limit: int = typer.Option(0, "--limit", help="Cap number sent (0 = no limit)"),
) -> None:
    """Send all attempts currently in status=queued."""
    init_db()
    with get_session() as session:
        ids = [
            r.id
            for r in session.execute(
                select(OutreachAttemptRow).where(OutreachAttemptRow.status == "queued")
            )
            .scalars()
            .all()
        ]
    if limit > 0:
        ids = ids[:limit]
    if not ids:
        console.print("[yellow]Nothing queued to send.[/yellow]")
        return
    console.print(f"[bold]Sending {len(ids)} attempts (dry_run={dry_run})...[/bold]")
    sent = 0
    failed = 0
    for aid in ids:
        with get_session() as session:
            try:
                send_outreach_attempt(session, aid, dry_run=dry_run)
                sent += 1
            except OutreachSendError as exc:
                console.print(f"  [red]#{aid} failed:[/red] {exc}")
                failed += 1
    console.print(f"[green]Sent {sent}[/green] / failed {failed}")


@outreach_app.command("poll")
def poll(no_classify: bool = typer.Option(False, "--no-classify")) -> None:
    """Pull replies from IMAP and optionally run the LLM classifier."""
    init_db()
    with get_session() as session:
        try:
            result = poll_replies(session)
        except ImapNotConfigured as exc:
            console.print(f"[red]IMAP not configured:[/red] {exc}")
            raise typer.Exit(code=2) from exc
    console.print(
        f"Examined {result.examined}, matched {result.matched_replies}, "
        f"unmatched {result.unmatched}"
    )
    if not no_classify:
        with get_session() as session:
            n = classify_pending(session)
        console.print(f"Classified {n} new replies.")


@outreach_app.command("status")
def status() -> None:
    """Show outreach summary counts and recent classifications."""
    init_db()
    with get_session() as session:
        by_status: dict[str, int] = {
            status: count
            for status, count in session.execute(
                select(OutreachAttemptRow.status, func.count()).group_by(OutreachAttemptRow.status)
            ).all()
        }
        by_class: dict[str, int] = {
            cls: count
            for cls, count in session.execute(
                select(OutreachReplyRow.classification, func.count()).group_by(
                    OutreachReplyRow.classification
                )
            ).all()
        }
        opt_outs = session.scalar(select(func.count()).select_from(OptOutRow))
    console.print("[bold]Attempts by status[/bold]")
    for k, v in sorted(by_status.items()):
        console.print(f"  {k}: {v}")
    console.print("\n[bold]Replies by classification[/bold]")
    if not by_class:
        console.print("  (none)")
    for k, v in sorted(by_class.items()):
        console.print(f"  {k}: {v}")
    console.print(f"\n[bold]Opt-outs:[/bold] {opt_outs}")
