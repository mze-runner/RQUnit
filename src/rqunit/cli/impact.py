"""`spec-impact` — classify manifest edits vs a git ref and print the §5.5
impact report. Exit 0 = additive-only (or no changes), 1 = mutating changes
present (they require Gate 1 with this report), 2 = tool error."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from ..impact import build_report, diff_manifests, manifest_at_ref, render
from ..schemas import repo_root
from ..store import Store


@click.command()
@click.option("--store", "store_path", type=click.Path(path_type=Path), default=None)
@click.option("--against", default="HEAD", help="Git ref holding the old manifest state.")
@click.option("--service", "services", multiple=True,
              help="Service(s) to diff; default: every manifest in the store.")
def main(store_path: Path | None, against: str, services: tuple[str, ...]) -> None:
    try:
        root = store_path or repo_root()
        store = Store.load(root)
    except Exception as e:
        click.echo(f"spec-impact: tool error: {e}", err=True)
        sys.exit(2)
    any_mutating = False
    for service, manifest in store.manifests().items():
        if services and service not in services:
            continue
        old = manifest_at_ref(root, against, service)
        changes = diff_manifests(old or {}, manifest.raw)
        if old is None:
            changes = [c for c in changes]  # whole manifest is new — all additive by construction
        report = build_report(store, service, changes)
        if report.changes:
            click.echo(render(report))
        any_mutating = any_mutating or bool(report.mutating)
    sys.exit(1 if any_mutating else 0)
