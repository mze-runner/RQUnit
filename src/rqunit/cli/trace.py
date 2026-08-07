"""`spec-trace` — traceability resolver + orphan reports + L14 diff gate."""

from __future__ import annotations

import json as jsonlib
import sys
from dataclasses import asdict
from pathlib import Path

import click

from ..schemas import repo_root
from ..store import Store
from ..strip import apply as apply_strip, plan as plan_strip
from ..trace import build_report, l14_gate, render_markdown, scan_tests


def _strip(store_path: Path | None, everything: bool, write: bool) -> None:
    """The off-ramp. Dry by default: this rewrites source the consumer owns,
    and a destructive default is how a tool gets run once and then distrusted."""
    try:
        root = store_path or repo_root()
        decided = plan_strip(Store.load(root), root, everything=everything)
        result = apply_strip(root, decided, write=write) if decided.total else None
    except Exception as e:
        click.echo(f"rqunit trace --strip: tool error: {e}", err=True)
        sys.exit(2)

    for name in decided.unavailable:
        click.echo(f"note: stack '{name}' declares no stripper role — its annotations "
                   f"were NOT removed ([stacks.{name}.adapter] stripper in rqunit.toml). "
                   "A stack that can be adopted but not un-adopted is a one-way door.",
                   err=True)

    scope = "every annotation" if everything else "annotations naming no active RU"
    if not decided.total:
        click.echo(f"trace --strip: nothing to remove ({scope})")
        sys.exit(0)

    for path in result.written:
        click.echo(f"  {'rewrote' if write else 'would rewrite'} {path}")
    click.echo(f"trace --strip: {len(result.stripped)} annotation(s) in "
               f"{len(result.written)} file(s) — {scope}")
    if not write:
        click.echo("\nNothing was written. Re-run with --apply to rewrite the sources; "
                   "commit them separately from any store change, so the off-ramp is "
                   "one reviewable diff.")
    sys.exit(0)


@click.command()
@click.option("--store", "store_path", type=click.Path(path_type=Path), default=None)
@click.option("--against", default=None,
              help="L14 diff gate: new untraced tests relative to this git ref are blocking.")
@click.option("--no-write", is_flag=True, help="Skip writing the orphan projections.")
@click.option("--strip", is_flag=True,
              help="The off-ramp: remove trace annotations naming no active RU. Reports "
                   "what it would remove; pass --apply to rewrite the sources.")
@click.option("--all", "everything", is_flag=True,
              help="With --strip: remove EVERY annotation, `infrastructure` markers "
                   "included. Off-boarding, not migration.")
@click.option("--apply", is_flag=True,
              help="With --strip: actually rewrite the sources. Without it nothing on "
                   "disk changes — this edits code the consumer owns.")
def main(store_path: Path | None, against: str | None, no_write: bool,
         strip: bool, everything: bool, apply: bool) -> None:
    if (everything or apply) and not strip:
        click.echo("rqunit trace: --all and --apply mean nothing without --strip", err=True)
        sys.exit(2)
    if strip:
        _strip(store_path, everything, apply)
        return
    try:
        root = store_path or repo_root()
        store = Store.load(root)
        checks = scan_tests(root)         # one observation feeds both consumers
        report = build_report(store, root, checks=checks)
        gate = l14_gate(store, root, against, head=checks) if against else []
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
    for name in report.unscanned_stacks:
        click.echo(f"note: stack '{name}' declares no scanner role — its tests are "
                   "not observed ([stacks."
                   f"{name}.adapter] scanner in rqunit.toml)", err=True)
    click.echo(
        f"trace: {len(report.unverified_rus)} unverified RU(s), "
        f"{len(report.untraced_checks)} untraced check(s) (burn-down), "
        f"{len(report.infrastructure)} infrastructure, "
        f"{len(report.orphan_facts)} orphan fact(s)"
    )
    sys.exit(1 if (report.blocking or gate) else 0)
