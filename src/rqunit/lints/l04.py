"""L4 — source_ref resolves to an existing INT artifact with a valid anchor
(spec §10.1, §4). The anchor names lines, and they must fall inside the file.

Section anchors (`#S<slug>`) were in the grammar from the start and were never
enforceable: an intent is "any (MD, transcript)", so a pasted conversation has
no headings to slugify, and L4 could only ever check that the FILE existed. An
anchor pointing at a section that was never there passed forever. v0.16.0
retires the form rather than pinning a markdown slug rule into core for the
one capture format that happens to have headings.

**Every artifact whose schema requires `source_ref`, not only RUs.** A FEAT
carries one under the identical grammar, and for eleven revisions nothing
resolved it: the pattern enforced the anchor's SHAPE, which is why the link read
as covered while pointing at nothing. That is load-bearing rather than cosmetic,
because a manifest endpoint's required `ru` link admits `FEAT-<slug>` — the
incremental adoption path — so a surface's whole traceability chain could
terminate at a FEAT anchored into a file that no longer exists. It bites hardest
during migration, where captures are re-cut as scope is learned and line ranges
move under anchors nobody re-checks. The resolution logic is one helper called
per kind, so a third artifact carrying `source_ref` cannot repeat the omission.
"""

import re

from .. import ids
from ..violations import Violation
from .base import lint, rel

_REF = re.compile(
    rf"^(?P<int>{ids.INTENT_BODY})#L(?P<start>[0-9]+)(?:-(?P<end>[0-9]+))?$")


@lint("L4")
def run(store):
    known = set(store.intents())
    out = []
    for artifact in (*store.rus(), *store.features()):
        out += _resolve(store, artifact, known)
    return out


def _resolve(store, artifact, known: set[str]) -> list[Violation]:
    ref = artifact.raw["source_ref"]
    m = _REF.match(ref)
    if not m:  # schema stage should have caught it; report anyway
        return [_v(store, artifact, f"source_ref {ref!r} is not a valid INT anchor")]
    int_id = m.group("int")
    if int_id not in known:
        return [_v(store, artifact,
                   f"source_ref targets {int_id}, which does not exist in spec/intent/")]
    # Always present now that the anchor is line-only — the branch that guarded
    # this was the section form's, and it is gone.
    start = int(m.group("start"))
    end = int(m.group("end") or start)
    lines = len(store.intent_path(int_id).read_text().splitlines())
    if start < 1 or end < start or end > lines:
        return [_v(store, artifact,
                   f"anchor L{m.group('start')}{'-' + m.group('end') if m.group('end') else ''} "
                   f"is outside {int_id} ({lines} lines)")]
    return []


def _v(store, artifact, message):
    return Violation(rule="L4", severity="error", artifact=artifact.id,
                     path=rel(store, artifact.path), message=message + ".",
                     suggestion="Anchor into a real, committed INT artifact (<INT id>#L<a>-<b>).")
