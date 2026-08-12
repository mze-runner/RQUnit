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

from .. import ids
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
    if not re.match(ids.permanent_pattern("RU"), ru_id):
        _fail("Gate 2 records attach to permanent ids (RU-<SEQUENCE> or "
              "RU-<SEGMENT>-<SEQUENCE>) — drafts are not reviewable.")
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
    never overwrite). The check-evidence ledger is append-only too, but by a
    different test: it legitimately grows on every recording, so what must
    hold is that the base content is still a PREFIX of the current one
    (§6.8)."""
    root = store_path or repo_root()
    proc = subprocess.run(
        ["git", "-C", str(root), "diff", "--name-status", against,
         "--", "spec/reviews", "spec/packets/*.packet.md"],
        capture_output=True, text=True)
    if proc.returncode != 0:
        click.echo(f"spec-review guard: git diff failed: {proc.stderr.strip()}", err=True)
        sys.exit(2)
    tampered = [f"append-only artifact tampered: {line}"
                for line in proc.stdout.splitlines()
                if line and not line.startswith("A")]
    tampered += _ledger_rewritten(Path(root), against)
    if tampered:
        for line in tampered:
            click.echo(line, err=True)
        sys.exit(1)
    click.echo("review records + packets + evidence ledger: append-only holds")


def _ledger_rewritten(root: Path, against: str) -> list[str]:
    """The evidence ledger's own append-only test. `git show` the base copy and
    require it to be a line-prefix of the current one: appending is the whole
    point, so the name-status rule the records use would fire on every honest
    recording."""
    from ..evidence import LEDGER_PATH

    relative = "/".join(LEDGER_PATH)
    shown = subprocess.run(
        ["git", "-C", str(root), "show", f"{against}:./{relative}"],
        capture_output=True, text=True)
    if shown.returncode != 0:
        return []          # absent at the base ref: everything in it is new
    base = shown.stdout.splitlines()
    path = root / relative
    current = path.read_text().splitlines() if path.is_file() else []
    if current[:len(base)] == base:
        return []
    return [f"append-only artifact tampered: {relative} — its recorded history "
            f"at {against} is no longer a prefix of the current file. Evidence is "
            "added to, never rewritten: a first that can be deleted proves "
            "nothing (§6.8)."]


def _fail(message: str) -> None:
    click.echo(f"spec-review: {message}", err=True)
    sys.exit(1)
