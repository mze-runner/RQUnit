"""L4 — source_ref resolves to an existing INT artifact with a valid anchor
(spec §10.1, §4). The anchor names lines, and they must fall inside the file.

Section anchors (`#S<slug>`) were in the grammar from the start and were never
enforceable: an intent is "any (MD, transcript)", so a pasted conversation has
no headings to slugify, and L4 could only ever check that the FILE existed. An
anchor pointing at a section that was never there passed forever. v0.16.0
retires the form rather than pinning a markdown slug rule into core for the
one capture format that happens to have headings."""

import re

from .. import ids
from ..violations import Violation
from .base import lint, rel

_REF = re.compile(
    rf"^(?P<int>{ids.INTENT_BODY})#L(?P<start>[0-9]+)(?:-(?P<end>[0-9]+))?$")


@lint("L4")
def run(store):
    out = []
    known = set(store.intents())
    for ru in store.rus():
        m = _REF.match(ru.raw["source_ref"])
        if not m:  # schema stage should have caught it; report anyway
            out.append(_v(store, ru, f"source_ref {ru.raw['source_ref']!r} is not a valid INT anchor"))
            continue
        int_id = m.group("int")
        if int_id not in known:
            out.append(_v(store, ru, f"source_ref targets {int_id}, which does not exist in spec/intent/"))
            continue
        # Always present now that the anchor is line-only — the branch that
        # guarded this was the section form's, and it is gone.
        start = int(m.group("start"))
        end = int(m.group("end") or start)
        lines = len(store.intent_path(int_id).read_text().splitlines())
        if start < 1 or end < start or end > lines:
            out.append(_v(store, ru,
                          f"anchor L{m.group('start')}{'-' + m.group('end') if m.group('end') else ''} "
                          f"is outside {int_id} ({lines} lines)"))
    return out


def _v(store, ru, message):
    return Violation(rule="L4", severity="error", artifact=ru.id, path=rel(store, ru.path),
                     message=message + ".",
                     suggestion="Anchor into a real, committed INT artifact (<INT id>#L<a>-<b>).")
