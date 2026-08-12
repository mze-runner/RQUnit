"""`rqunit check` — the consistency checks; mirrors the lint report contract."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from ..checks.base import run_checks
from ..errors import StoreError
from ..schemas import repo_root
from ..store import Store
from ..violations import (build_report, empty_store_findings, exit_code,
                          render_text, resolve_format, schema_violation)


@click.command()
@click.option("--store", "store_path", type=click.Path(path_type=Path), default=None,
              help="Store root (directory containing spec/). Defaults to the repo root.")
@click.option("--only", default=None, help="Run a single check, e.g. --only C4.")
@click.option("--format", "fmt", type=click.Choice(["json", "text"]), default=None,
              help="Output shape. Default: text on a terminal, JSON when piped.")
@click.option("--strict", is_flag=True, help="Warnings also fail the run.")
def main(store_path: Path | None, only: str | None, fmt: str | None, strict: bool) -> None:
    fmt = resolve_format(fmt)
    try:
        root = store_path or repo_root()
    except FileNotFoundError as e:
        click.echo(str(e), err=True)
        sys.exit(2)
    try:
        store = Store.load(root)
        violations = run_checks(store, only=only)
        violations += empty_store_findings(store)
        checked = (len(store.rus()) + len(store.features()) + len(store.gaps())
                   + len(store.manifests()) + len(store.models()) + len(store.intents()))
    except StoreError as e:
        violations = [schema_violation(e, root)]
        checked = 0
    except Exception as e:
        click.echo(f"spec-check: tool error: {e}", err=True)
        sys.exit(2)
    report = build_report("spec-check", violations, checked, root)
    click.echo(json.dumps(report, indent=2) if fmt == "json" else render_text(report))
    sys.exit(exit_code(report, strict=strict))
