"""Email digest of new watch matches.

Uses stdlib smtplib (synchronous). Phase 3 outreach will move to Postmark/SES, but for
self-notifications a plain SMTP path (e.g. Gmail app password) is fine.
"""
from __future__ import annotations

import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from html import escape

from guitar_searcher.config import get_settings
from guitar_searcher.matching.score import ScoredListing
from guitar_searcher.schemas import QuerySpec
from guitar_searcher.utils.logging import get_logger

log = get_logger(__name__)


class EmailNotConfigured(RuntimeError):
    """Raised when SMTP env vars aren't all populated."""


@dataclass
class SmtpSender:
    host: str
    port: int
    username: str
    password: str
    use_tls: bool
    sender: str

    @classmethod
    def from_settings(cls) -> SmtpSender:
        s = get_settings()
        missing = [
            name
            for name, value in (
                ("GS_SMTP_HOST", s.smtp_host),
                ("GS_SMTP_USERNAME", s.smtp_username),
                ("GS_SMTP_PASSWORD", s.smtp_password),
                ("GS_NOTIFY_FROM", s.notify_from),
            )
            if not value
        ]
        if missing:
            raise EmailNotConfigured(f"SMTP not fully configured; missing: {', '.join(missing)}")
        return cls(
            host=s.smtp_host,
            port=s.smtp_port,
            username=s.smtp_username,
            password=s.smtp_password,
            use_tls=s.smtp_use_tls,
            sender=s.notify_from,
        )

    def send(self, to: str, subject: str, text_body: str, html_body: str | None = None) -> None:
        msg = EmailMessage()
        msg["From"] = self.sender
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(text_body)
        if html_body:
            msg.add_alternative(html_body, subtype="html")

        if self.use_tls:
            context = ssl.create_default_context()
            with smtplib.SMTP(self.host, self.port, timeout=30) as srv:
                srv.starttls(context=context)
                srv.login(self.username, self.password)
                srv.send_message(msg)
        else:
            with smtplib.SMTP_SSL(self.host, self.port, timeout=30) as srv:
                srv.login(self.username, self.password)
                srv.send_message(msg)


def render_digest(
    watch_name: str, query: QuerySpec, new_matches: list[ScoredListing]
) -> tuple[str, str, str]:
    """Return (subject, text_body, html_body)."""
    n = len(new_matches)
    subject = f"[guitar-searcher] {n} new {'match' if n == 1 else 'matches'} for {watch_name or query.display()}"

    text_lines = [
        f"Watch: {watch_name or '(unnamed)'}",
        f"Query: {query.display()}",
        f"New matches: {n}",
        "",
    ]
    for i, s in enumerate(new_matches, 1):
        listing = s.listing
        price = f"${listing.price_usd:,.0f}" if listing.price_usd is not None else "price n/a"
        year = str(listing.year) if listing.year else "—"
        text_lines.append(
            f"{i}. [{s.score:.2f}] {listing.shop_name} | {listing.raw_title} | {year} | {price}"
        )
        text_lines.append(f"   {listing.url}")
        text_lines.append(f"   why: {s.reasoning}")
        text_lines.append("")

    html_rows = []
    for i, s in enumerate(new_matches, 1):
        listing = s.listing
        price = f"${listing.price_usd:,.0f}" if listing.price_usd is not None else "—"
        year = str(listing.year) if listing.year else "—"
        html_rows.append(
            "<tr>"
            f"<td>{i}</td>"
            f"<td>{s.score:.2f}</td>"
            f"<td>{escape(listing.shop_name)}</td>"
            f"<td><a href=\"{escape(str(listing.url))}\">{escape(listing.raw_title)}</a></td>"
            f"<td>{year}</td>"
            f"<td style=\"text-align:right\">{price}</td>"
            f"<td><em>{escape(s.reasoning)}</em></td>"
            "</tr>"
        )
    html_body = f"""
    <html><body style="font-family:-apple-system,Segoe UI,sans-serif">
      <h2>{escape(watch_name or '(unnamed)')}</h2>
      <p><strong>Query:</strong> {escape(query.display())}<br>
      <strong>New matches:</strong> {n}</p>
      <table cellpadding="6" cellspacing="0" border="1" style="border-collapse:collapse">
        <thead><tr>
          <th>#</th><th>Score</th><th>Shop</th><th>Listing</th>
          <th>Year</th><th>Price</th><th>Why</th>
        </tr></thead>
        <tbody>{"".join(html_rows)}</tbody>
      </table>
    </body></html>
    """
    return subject, "\n".join(text_lines), html_body


def send_match_digest(
    watch_name: str,
    query: QuerySpec,
    new_matches: list[ScoredListing],
    *,
    sender: SmtpSender | None = None,
    recipient: str | None = None,
) -> None:
    if not new_matches:
        return
    sender = sender or SmtpSender.from_settings()
    recipient = recipient or get_settings().notify_to
    if not recipient:
        raise EmailNotConfigured("GS_NOTIFY_TO not set")
    subject, text, html = render_digest(watch_name, query, new_matches)
    sender.send(recipient, subject, text, html)
    log.info("notify.sent", watch=watch_name, count=len(new_matches), to=recipient)
