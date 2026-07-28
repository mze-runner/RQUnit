"""`rqunit report` — the management-facing snapshot.

Writes a self-contained HTML file (no external assets, prints cleanly), or the
underlying `report-data.json` contract with --format json. Deliberately NOT a
committed projection: it carries a generation timestamp, so it would break the
byte-currency guarantee that makes `generate check` meaningful.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from ..errors import StoreError
from ..report import build_data, render_html, render_json
from ..schemas import repo_root
from ..store import Store


@click.command()
@click.option("--store", "store_path", type=click.Path(path_type=Path), default=None,
              help="Store root (directory containing spec/). Defaults to the repo root.")
@click.option("--out", "out_path", type=click.Path(path_type=Path), default=None,
              help="Output file (default: rqunit-report.html, or - for stdout).")
@click.option("--format", "fmt", type=click.Choice(["html", "json"]), default="html")
def main(store_path: Path | None, out_path: Path | None, fmt: str) -> None:
    """Render a requirements report: coverage, status, gate activity, burn-down."""
    try:
        root = Path(store_path or repo_root())
        store = Store.load(root)
        data = build_data(store, root)
    except StoreError as e:
        click.echo(f"rqunit report: store does not load — fix that first: {e}", err=True)
        sys.exit(2)
    except Exception as e:
        click.echo(f"rqunit report: tool error: {e}", err=True)
        sys.exit(2)

    content = render_html(data) if fmt == "html" else render_json(data)
    if str(out_path) == "-":
        click.echo(content, nl=False)
        return
    target = Path(out_path) if out_path else root / f"rqunit-report.{fmt}"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    totals = data["totals"]["rus"]
    click.echo(f"{target}: {totals.get('active', 0)} active requirements, "
               f"{len(data['gates']['sittings'])} Gate 1 sitting(s), "
               f"{len(data['health'])} health finding(s)")
