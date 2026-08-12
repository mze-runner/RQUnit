"""`rqunit doctor` — structural health of the store (not rule compliance).

Advisory by design: exit 0 unless --strict, so it never becomes a gate people
learn to ignore. Rule violations belong to `lint` and `check`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from ..doctor import run as run_doctor
from ..errors import StoreError
from ..schemas import repo_root
from ..store import Store
from ..violations import resolve_format


@click.command()
@click.option("--store", "store_path", type=click.Path(path_type=Path), default=None,
              help="Store root (directory containing spec/). Defaults to the repo root.")
@click.option("--format", "fmt", type=click.Choice(["json", "text"]), default=None,
              help="Output shape. Default: text on a terminal, JSON when piped.")
@click.option("--strict", is_flag=True, help="Warning-severity findings fail the run.")
def main(store_path: Path | None, fmt: str | None, strict: bool) -> None:
    """Report structural problems: lost RUs, orphaned artifacts, dangling
    review records, and a stale branch that would make activation collide."""
    fmt = resolve_format(fmt)
    try:
        root = store_path or repo_root()
        store = Store.load(root)
        findings = run_doctor(store, Path(root))
    except StoreError as e:
        click.echo(f"rqunit doctor: store does not load — fix that first: {e}", err=True)
        sys.exit(2)
    except Exception as e:
        click.echo(f"rqunit doctor: tool error: {e}", err=True)
        sys.exit(2)

    if fmt == "json":
        click.echo(json.dumps({"findings": [f.__dict__ for f in findings]}, indent=2))
    else:
        warnings = [f for f in findings if f.severity == "warning"]
        infos = [f for f in findings if f.severity == "info"]
        click.echo(f"rqunit doctor · {len(warnings)} warning(s), {len(infos)} note(s)")
        for finding in warnings + infos:
            click.echo(f"\n[{finding.severity}/{finding.kind}] {finding.message}")
            click.echo(f"    {finding.suggestion}")
        if not findings:
            click.echo("\nstore is structurally sound.")
    sys.exit(1 if strict and any(f.severity == "warning" for f in findings) else 0)
