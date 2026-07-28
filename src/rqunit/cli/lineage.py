"""`rqunit lineage` — the elaboration timeline of one feature, computed on
demand from provenance the store already carries: INT source anchors, gate
stamps, supersession links, GAP records, and Gate 2 review records.

A QUERY verb, deliberately not a projection: nothing is written, committed,
or currency-checked. The reliable clock is `gate1_stamp.at` (sittings) and
Gate 2 record timestamps — INT captures and drafts carry no machine dates, so
they render as sections, never as dated events.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from ..schemas import repo_root
from ..status import compute, gate2_records
from ..store import Store


@click.command()
@click.argument("artifact_id")
@click.option("--store", "store_path", type=click.Path(path_type=Path), default=None)
def main(artifact_id: str, store_path: Path | None) -> None:
    """Print the lineage of FEAT-<slug> (or of the feature RU-XXXX belongs to)."""
    root = Path(store_path or repo_root())
    store = Store.load(root)

    feat_id = artifact_id
    if artifact_id.startswith("RU-"):
        ru = next((r for r in store.rus() if r.id == artifact_id), None)
        if ru is None:
            _fail(f"{artifact_id} does not exist in the store.")
        feat_id = ru.raw.get("feature")
        if not feat_id:
            _fail(f"{artifact_id} carries no feature link — lineage is per-FEAT.")
    feat = next((f for f in store.features() if f.id == feat_id), None)
    if feat is None:
        _fail(f"{feat_id} does not exist in the store.")

    rus = [r for r in store.rus() if r.raw.get("feature") == feat_id]
    superseded_by = {r.raw["supersedes"]: r.id for r in store.rus() if r.raw.get("supersedes")}

    click.echo(f"{feat_id} — {' '.join(feat.raw['goal'].split())}")

    click.echo("\nIntent sources:")
    ints = sorted({r.raw["source_ref"].split("#", 1)[0] for r in rus if r.raw.get("source_ref")})
    for int_id in ints:
        path = store.intent_path(int_id)
        click.echo(f"- {int_id}" + (f" ({path.relative_to(root)})" if path else ""))
    if not ints:
        click.echo("(none)")

    click.echo("\nTimeline:")
    events: list[tuple[str, str]] = []
    sittings: dict[tuple[str, str], list[str]] = {}
    for r in rus:
        stamp = r.raw.get("gate1_stamp")
        if stamp:
            label = r.id
            if r.raw.get("supersedes"):
                label += f" (supersedes {r.raw['supersedes']})"
            sittings.setdefault((stamp["at"], stamp["by"]), []).append(label)
    for (at, by), labels in sittings.items():
        events.append((at, f"Gate 1 ({by}): activated {', '.join(sorted(labels))}"))
    for r in rus:
        for rec in gate2_records(store, r.id):
            events.append((rec.get("at", ""),
                           f"Gate 2 ({rec.get('reviewer', '?')}): {rec.get('verdict', '?')} — "
                           f"{r.id} \"{rec.get('criterion', '')}\""))
    for at, text in sorted(events):
        click.echo(f"- {at} — {text}")
    if not events:
        click.echo("(no dated events — nothing activated or reviewed yet)")

    click.echo("\nGaps:")
    ru_ids = {r.id for r in rus} | {r.raw["draft_id"] for r in rus if r.raw.get("draft_id")}
    related = [g for g in store.gaps()
               if set(g.raw.get("affected") or []) & (ru_ids | {feat_id})]
    for gap in related:
        head = f"- {gap.id} ({gap.severity}, {gap.raw.get('status', '?')}"
        resolution = gap.raw.get("resolution") or {}
        if resolution.get("int_ref"):
            head += f" → {resolution['int_ref']}"
        question = " ".join(str(gap.raw.get("question", "")).split())
        click.echo(head + f"): {question[:120]}{'…' if len(question) > 120 else ''}")
    if not related:
        click.echo("(none)")

    click.echo("\nRequirement units:")
    for r in rus:
        s = compute(store, r)
        label = ("failing" if s.failing else "blocked" if s.blocked
                 else "done" if s.done else "debt" if s.debt else "pending")
        line = f"- {r.id} {r.status} (computed: {label})"
        if r.status == "superseded" and r.id in superseded_by:
            line += f" → superseded by {superseded_by[r.id]}"
        if r.raw.get("rationale_ref"):
            line += f" [rationale: {r.raw['rationale_ref']}]"
        click.echo(line + f": {' '.join(r.raw['statement'].split())}")
    if not rus:
        click.echo("(none)")


def _fail(message: str) -> None:
    click.echo(f"rqunit lineage: {message}", err=True)
    sys.exit(2)
