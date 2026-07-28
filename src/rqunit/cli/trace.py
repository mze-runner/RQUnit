"""`spec-trace` — traceability resolver + orphan reports + L14 diff gate."""

from __future__ import annotations

import json as jsonlib
import sys
from dataclasses import asdict
from pathlib import Path

import click

from ..schemas import repo_root
from ..store import Store
from ..trace import build_report, l14_gate, render_markdown


@click.command()
@click.option("--store", "store_path", type=click.Path(path_type=Path), default=None)
@click.option("--against", default=None,
              help="L14 diff gate: new untraced tests relative to this git ref are blocking.")
@click.option("--no-write", is_flag=True, help="Skip writing the orphan projections.")
def main(store_path: Path | None, against: str | None, no_write: bool) -> None:
    try:
        root = store_path or repo_root()
        store = Store.load(root)
        report = build_report(store, root)
        gate = l14_gate(store, root, against) if against else []
    except Exception as e:
        click.echo(f"spec-trace: tool error: {e}", err=True)
        sys.exit(2)

    if not no_write:
        projections = Path(root) / "spec" / "projections"
        if projections.is_dir():
            markdown = render_markdown(report)
            payload = jsonlib.dumps(asdict(report), indent=2) + "\n"
            for name, content in (("orphans.md", markdown), ("orphans.json", payload)):
                target = projections / name
                if not target.exists() or target.read_text() != content:
                    target.write_text(content)

    for line in report.blocking:
        click.echo(f"ERROR {line}", err=True)
    for line in gate:
        click.echo(f"ERROR {line}", err=True)
    click.echo(
        f"trace: {len(report.unverified_rus)} unverified RU(s), "
        f"{len(report.untraced_checks)} untraced check(s) (burn-down), "
        f"{len(report.infrastructure)} infrastructure, "
        f"{len(report.orphan_facts)} orphan fact(s)"
    )
    sys.exit(1 if (report.blocking or gate) else 0)
