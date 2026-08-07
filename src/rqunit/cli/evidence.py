"""`rqunit evidence` — the check-evidence ledger (spec §6.8).

`record` folds one test run's observations into the store's append-only
ledger, keeping only firsts. Run it wherever the suite runs: the ledger is
what lets L26 tell a check that has demonstrated it can fail from one that
has only ever been green.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import click

from ..config import load as load_config
from ..errors import StoreError
from ..evidence import append, fold, ledger_path, load_ledger, never_red
from ..invoke import run_role, validate_payload
from ..schemas import repo_root

SCHEMA = "check-evidence.schema.json"


@click.group()
def main() -> None:
    """Check-evidence ledger."""


@main.command()
@click.option("--store", "store_path", type=click.Path(path_type=Path), default=None,
              help="Store root (directory containing spec/). Defaults to the repo root.")
@click.option("--from", "from_paths", multiple=True, type=click.Path(path_type=Path),
              help="Observation artifact(s) to fold in; defaults to every stack's "
                   "declared evidence role.")
def record(store_path: Path | None, from_paths: tuple[Path, ...]) -> None:
    """Fold a run's observations into the ledger, recording only firsts."""
    try:
        root = Path(store_path or repo_root())
        runs = _observations(root, from_paths)
        if not runs:
            click.echo("rqunit evidence: no evidence configured "
                       "([stacks.<name>.adapter] evidence = { cmd = [...] } or "
                       "{ artifact = \"...\" } in rqunit.toml), and no --from given",
                       err=True)
            sys.exit(2)
        # One stamp for the whole recording: the firsts were all demonstrated
        # by the same run, and a probe may not stamp its own output (its
        # bytes must be a deterministic function of its input).
        at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        added = []
        for source, artifact in runs:
            fresh = fold(root, artifact, at=at, source=source)
            append(root, fresh)
            added.extend(fresh)
    except StoreError as e:
        click.echo(f"rqunit evidence: {e}", err=True)
        sys.exit(2)

    for entry in added:
        click.echo(f"{entry.observation}: {entry.check_id}")
    total = len(load_ledger(root))
    click.echo(f"evidence: {len(added)} first(s) recorded from {len(runs)} run(s); "
               f"{total} in the ledger ({ledger_path(root).relative_to(root)}). "
               f"{len(never_red(root))} check(s) green and never observed failing.")


def _observations(root: Path, from_paths: tuple[Path, ...]) -> list[tuple[str, dict]]:
    """Every run to fold: explicit artifacts, or each stack's declared role."""
    if from_paths:
        out = []
        for path in from_paths:
            try:
                data = json.loads(Path(path).read_text())
            except OSError as e:
                raise StoreError(str(path), f"cannot read: {e}") from e
            except json.JSONDecodeError as e:
                raise StoreError(str(path), f"not parseable JSON: {e}") from e
            out.append((str(path), validate_payload(data, SCHEMA, str(path))))
        return out

    out = []
    for stack in load_config(root).stacks:
        if stack.adapter.evidence is None:
            continue
        role = stack.adapter.evidence
        where = (str(root / role.artifact) if role.artifact
                 else f"[stacks.{stack.name}.adapter] evidence")
        out.append((where, run_role(root, stack, "evidence", schema=SCHEMA)))
    return out
