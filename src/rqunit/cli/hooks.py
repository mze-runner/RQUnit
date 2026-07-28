"""`spec-hooks` — runtime enforcement entry points (H1/H2). Failure posture
(plan D-P5.4): tool errors never brick editing — only a CONFIRMED
must_not_touch match exits 1; H2 always exits 0."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from ..hooks import append_audit, h1_verdict, h2_record
from ..schemas import repo_root


@click.group()
def main() -> None:
    """H1/H2 scope hooks."""


@main.command()
@click.option("--store", "store_path", type=click.Path(path_type=Path), default=None)
@click.option("--path", "file_path", required=True)
def h1(store_path, file_path) -> None:
    """Pre-write guard: exit 1 (block) iff the path is inside must_not_touch."""
    try:
        root = store_path or repo_root()
        blocked, message = h1_verdict(root, file_path)
    except Exception as e:  # never brick editing on tooling failure
        click.echo(f"spec-hooks h1: non-blocking tool error: {e}", err=True)
        sys.exit(0)
    if blocked:
        click.echo(message, err=True)
        sys.exit(1)
    sys.exit(0)


@main.command()
@click.option("--store", "store_path", type=click.Path(path_type=Path), default=None)
@click.option("--path", "file_path", required=True)
def h2(store_path, file_path) -> None:
    """Post-write auditor: append out-of-owns writes to the scope audit log.
    NEVER blocks — exit 0 even on violation (spec §10.3 H2)."""
    try:
        root = store_path or repo_root()
        record = h2_record(root, file_path)
        if record:
            append_audit(root, record)
            click.echo(f"H2: audited out-of-owns write {record['path']} (task {record['task']})")
    except Exception as e:
        click.echo(f"spec-hooks h2: non-blocking tool error: {e}", err=True)
    sys.exit(0)
