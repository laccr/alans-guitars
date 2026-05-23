from __future__ import annotations

import typer

from guitar_searcher.cli import outreach as outreach_cmd
from guitar_searcher.cli import search as search_cmd
from guitar_searcher.cli import shops as shops_cmd
from guitar_searcher.cli import watch as watch_cmd
from guitar_searcher.config import get_settings
from guitar_searcher.utils.logging import configure_logging

app = typer.Typer(
    name="guitar-searcher",
    help="Hunt for specific guitars across the US guitar retail web.",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def _root() -> None:
    configure_logging(level=get_settings().log_level)


app.command(name="search", help="Search for guitars matching a spec.")(search_cmd.search)
app.add_typer(shops_cmd.shops_app, name="shops", help="Manage the shop directory.")
app.add_typer(watch_cmd.watch_app, name="watch", help="Saved watches and notifications.")
app.add_typer(outreach_cmd.outreach_app, name="outreach", help="Email outreach to shops.")


if __name__ == "__main__":
    app()
