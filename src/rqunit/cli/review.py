"""`spec-review` — append-only Gate 2 verdict records (TASK-053, spec §7.2,
formats §9). Records enter ONLY through this CLI: agent file-writes into
spec/reviews/ are denied by a PreToolUse hook (no self-certification), and the
`guard` subcommand makes CI reject modification or deletion of existing
records."""

from __future__ import annotations

import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import click
import yaml

from ..schemas import repo_root


@click.group()
def main() -> None:
    """Gate 2 review records."""


@main.command()
@click.argument("ru_id")
@click.option("--store", "store_path", type=click.Path(path_type=Path), default=None)
@click.option("--verdict", type=click.Choice(["pass", "fail"]), required=True)
@click.option("--criterion", required=True,
              help="Must match the RU's human-verification criterion verbatim.")
@click.option("--note", default="")
@click.option("--reviewer", required=True)
@click.option("--packet", default="", help="The TASK packet whose output was judged.")
def record(ru_id, store_path, verdict, criterion, note, reviewer, packet) -> None:
    if not re.match(r"^RU-[0-9]{4}$", ru_id):
        _fail("Gate 2 records attach to permanent ids (RU-XXXX) — drafts are not reviewable.")
    if "@" in reviewer:
        _fail(f"reviewer '{reviewer}' looks like contact info — use a stable handle; "
              "the store is published, emails never enter it (formats §9).")
    root = store_path or repo_root()
    if not (Path(root) / "spec" / "ru" / f"{ru_id}.yaml").is_file():
        _fail(f"{ru_id} does not exist in the store.")
    now = datetime.now(timezone.utc)
    slug = re.sub(r"[^a-z0-9]+", "-", criterion.lower()).strip("-")[:40] or "review"
    directory = Path(root) / "spec" / "reviews" / ru_id
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{now.strftime('%Y%m%dT%H%M%SZ')}-{slug}.yaml"
    if path.exists():
        _fail(f"{path.name} already exists — records are append-only, never overwritten.")
    payload = {"ru": ru_id, "criterion": criterion, "verdict": verdict,
               "note": note, "reviewer": reviewer,
               "at": now.isoformat(timespec="seconds"), "packet": packet or None}
    path.write_text(yaml.safe_dump({k: v for k, v in payload.items() if v is not None},
                                   sort_keys=False, allow_unicode=True))
    click.echo(f"recorded {verdict} for {ru_id}: {path.relative_to(root)}")


@main.command()
@click.option("--store", "store_path", type=click.Path(path_type=Path), default=None)
@click.option("--against", required=True, help="Base git ref (e.g. origin/integration).")
def guard(store_path, against) -> None:
    """CI guard: any modification or deletion of an EXISTING review record OR
    committed task packet relative to the base ref fails the run — both are
    append-only (§7.2 records; §9.1 packets, plan D-P8.4: re-runs version,
    never overwrite)."""
    root = store_path or repo_root()
    proc = subprocess.run(
        ["git", "-C", str(root), "diff", "--name-status", against,
         "--", "spec/reviews", "spec/packets/*.packet.md"],
        capture_output=True, text=True)
    if proc.returncode != 0:
        click.echo(f"spec-review guard: git diff failed: {proc.stderr.strip()}", err=True)
        sys.exit(2)
    tampered = [line for line in proc.stdout.splitlines()
                if line and not line.startswith("A")]
    if tampered:
        for line in tampered:
            click.echo(f"append-only artifact tampered: {line}", err=True)
        sys.exit(1)
    click.echo("review records + packets: append-only holds")


def _fail(message: str) -> None:
    click.echo(f"spec-review: {message}", err=True)
    sys.exit(1)
