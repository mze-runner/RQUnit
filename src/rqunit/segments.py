"""The segment registry (formats §1; the design behind it: `identity-scheme-design.md`).

A segment is the domain an id is allocated into: `RU-ORD-01A2`. It is an
allocation and ownership boundary and **never a verification boundary** — C1
compares RUs against each other, C9 spans services, and L13 caps constitutional
RUs store-wide, a number that is only meaningful because it is global. Every
rule stays store-wide; nothing in the framework partitions by segment.

`spec/framework/segments.yaml` is the store's declaration of which domains
exist, beside the tag and actor vocabularies, because it is the same kind of
thing: consumer-owned vocabulary, Gate-1-governed, starting empty. A store with
no file has no segments, and its ids carry none — which is a complete and
supported state, not a store that has not got round to it yet.

**A segment name is unique among the store's vocabularies in being permanent.**
Tags are re-cut freely and actors renamed with a sweep, because they appear only
in artifacts this repository controls. A segment appears in filenames, in gate
stamps, in Gate 2 review directory names, in committed packets, and in
`verifies:` annotations inside the consumer's own source. Renaming one is not a
rename; it is a mass supersession. So the registry admits exactly two edits —
add a segment, and close one — and C16 exists to make the third and fourth
impossible to do quietly.

Closing is the retirement path: a closed segment allocates nothing further and
its existing ids keep working forever. Removing the entry instead would leave
those ids naming a domain the store no longer declares, which is the silent
failure this module is built to refuse.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .errors import BadConfig

SEGMENTS_PATH = ("spec", "framework", "segments.yaml")


def load_segments(root: Path) -> list[dict]:
    """Declared segments, or [] when the store carries no file.

    Malformed entries are RETURNED rather than filtered, for the reason the
    shim registry gives: dropping a bare `- ORD` would leave the segment
    reading as undeclared, and the consumer chasing a violation about a segment
    they believe they just declared. C16 reports the shape instead."""
    path = Path(root).joinpath(*SEGMENTS_PATH)
    if not path.is_file():
        return []
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as e:
        raise BadConfig(str(path), f"not parseable YAML: {e}") from e
    entries = data.get("segments") or []
    if not isinstance(entries, list):
        raise BadConfig(str(path), "`segments` must be a list of segment entries")
    return list(entries)


def declared(root: Path) -> set[str]:
    """Segment names the store declares — open and closed alike.

    A closed segment is still declared: its ids remain legal forever, and that
    is the whole difference between closing one and deleting it.

    A name is recovered from a MALFORMED entry too, where one is legible. A bare
    `- ORD` is the wrong shape, but it is not a store that stopped declaring
    ORD, and treating it as one would tell a consumer who mis-indented a line
    that they had committed the one edit that cannot be undone. The shape error
    is reported on its own; panic is not a diagnostic."""
    out = set()
    for entry in load_segments(root):
        name = str(entry.get("name") or "") if isinstance(entry, dict) else str(entry or "")
        if name:
            out.add(name)
    return out


def open_segments(root: Path) -> set[str]:
    """Segments that may still receive allocations.

    A malformed entry counts as OPEN, not closed. `declared` recovers its name
    so a mis-indented line is not mistaken for the irreversible edit; if this
    then withheld it, the caller would say "that segment is closed" about a
    segment nobody closed, and send the reader to delete a `closed: true` that
    is not there. Malformed is malformed — C16 says so, in those words."""
    return {name for name in declared(root)
            if not any(e.get("closed") for e in load_segments(root)
                       if isinstance(e, dict) and str(e.get("name") or "") == name)}
