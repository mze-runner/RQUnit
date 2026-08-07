"""`spec-generate` — conformance generation (TASK-070…072)."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from ..errors import StoreError
from ..generate import check_current, missing_emitter, scan_literals, write_all
from ..schemas import repo_root
from ..store import Store


@click.group()
def main() -> None:
    """Conformance generation."""


def _load(store_path: Path | None) -> tuple[Path, Store]:
    try:
        root = store_path or repo_root()
        return root, Store.load(root)
    except StoreError as e:
        click.echo(f"rqunit generate: {e}", err=True)
        sys.exit(2)


@main.command()
@click.option("--store", "store_path", type=click.Path(path_type=Path), default=None)
def all(store_path) -> None:
    """(Re)generate every artifact: constants, statechart suites, test plan,
    trace map, index, surface sheets."""
    root, store = _load(store_path)
    try:
        if (problem := missing_emitter(store, root)):
            click.echo(f"rqunit generate: {problem}", err=True)
            sys.exit(2)
        written = write_all(store, root)
    except StoreError as e:
        click.echo(f"rqunit generate: {e}", err=True)
        sys.exit(2)
    for path in written:
        click.echo(f"wrote {path.relative_to(root)}")
    click.echo(f"{len(written)} file(s) updated")


@main.command()
@click.option("--store", "store_path", type=click.Path(path_type=Path), default=None)
def check(store_path) -> None:
    """Fail if any generated artifact is stale, missing, or hand-edited."""
    root, store = _load(store_path)
    try:
        if (problem := missing_emitter(store, root)):
            click.echo(f"rqunit generate: {problem}", err=True)
            sys.exit(2)
        problems = check_current(store, root)
    except StoreError as e:
        click.echo(f"rqunit generate: {e}", err=True)
        sys.exit(2)
    for p in problems:
        click.echo(p, err=True)
    sys.exit(1 if problems else 0)


@main.command("scan-literals")
@click.option("--store", "store_path", type=click.Path(path_type=Path), default=None)
def scan(store_path) -> None:
    """Advisory (TASK-072): numeric literals in application tests equal to
    manifest values. Never affects exit code."""
    root, store = _load(store_path)
    for finding in scan_literals(store, root):
        click.echo(finding)
    sys.exit(0)
