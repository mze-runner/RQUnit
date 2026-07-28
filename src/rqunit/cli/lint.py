"""`spec-lint` — runs lints L1–L18 over a store (formats §4 report contract)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from ..errors import StoreError
from ..lints.base import run_lints
from ..schemas import repo_root
from ..store import Store
from ..violations import Violation, build_report, exit_code, render_text


@click.command()
@click.option("--store", "store_path", type=click.Path(path_type=Path), default=None,
              help="Store root (directory containing spec/). Defaults to the repo root.")
@click.option("--only", default=None, help="Run a single lint, e.g. --only L3.")
@click.option("--format", "fmt", type=click.Choice(["json", "text"]), default="json")
@click.option("--strict", is_flag=True, help="Warnings also fail the run.")
def main(store_path: Path | None, only: str | None, fmt: str, strict: bool) -> None:
    try:
        root = store_path or repo_root()
    except FileNotFoundError as e:
        click.echo(str(e), err=True)
        sys.exit(2)
    try:
        store = Store.load(root)
        violations = run_lints(store, only=only)
        checked = (len(store.rus()) + len(store.features()) + len(store.gaps())
                   + len(store.manifests()) + len(store.models()) + len(store.intents()))
    except StoreError as e:
        # A store that cannot load is itself the finding (schema stage red),
        # not a tool error.
        violations = [Violation(
            rule="SCHEMA", severity="error", artifact=Path(e.path).name if e.path else "store",
            path=e.path or str(root), message=str(e),
        )]
        checked = 0
    except Exception as e:  # tool failure — exit 2 per the CLI contract
        click.echo(f"spec-lint: tool error: {e}", err=True)
        sys.exit(2)
    report = build_report("spec-lint", violations, checked, root)
    if only in (None, "L20"):
        _write_suspect_queue(root, [v for v in violations if v.rule == "L20"])
    click.echo(json.dumps(report, indent=2) if fmt == "json" else render_text(report))
    sys.exit(exit_code(report, strict=strict))


def _write_suspect_queue(root: Path, findings) -> None:
    """spec/projections/suspect-queue.json (TASK-052, plan D-P4.4): refreshed
    when L20 findings exist, emptied when none. Entries only — no timestamp,
    so an unchanged queue produces no diff noise."""
    path = Path(root) / "spec" / "projections" / "suspect-queue.json"
    entries = [{"ru": v.artifact, "message": v.message} for v in findings]
    payload = json.dumps({"suspect": entries}, indent=2) + "\n"
    if not path.parent.is_dir():
        return  # not a full store (fixture subsets) — nothing to project
    if not path.exists() or path.read_text() != payload:
        path.write_text(payload)
