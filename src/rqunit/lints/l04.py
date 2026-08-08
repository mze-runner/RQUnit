"""L4 — source_ref resolves to an existing INT artifact with a valid anchor
(spec §10.1, §4). Line anchors must fall inside the file; section anchors are
checked for INT existence only in v1 (slug↔heading mapping is not yet pinned)."""

import re

from .. import ids
from ..violations import Violation
from .base import lint, rel

_REF = re.compile(
    rf"^(?P<int>{ids.INTENT_BODY})#(?:L(?P<start>[0-9]+)(?:-(?P<end>[0-9]+))?|S(?P<section>[a-z0-9-]+))$")


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
        if m.group("start"):
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
