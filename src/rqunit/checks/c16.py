"""C16 — every segment an id uses is declared, and the registry is well-formed.

Segments partition ALLOCATION, never verification, so this check is not about
what a segment contains. It is about the one property a segment has that no
other vocabulary in this store has: **permanence**.

The registry admits two edits, add and close. A rename and a removal are the
same event seen from the registry — the name stops being declared while ids in
`spec/ru/`, review directories, packets and consumer source still carry it —
and both are unrepairable, because ids are never rewritten. That makes "an id
uses a segment the store does not declare" the load-bearing violation here, and
the reason this is a check rather than a lint: it is a consistency question
between the registry and the ids.

The shape rules divide by whether a machine reads the value. An illegal or
duplicated `name` changes what the tools do — the id parses ambiguously, or
"is this closed" has two answers — so those are errors. A missing `domain`
changes only what a human understands, and "a non-blank string is present" is
all a machine can check of it, so that one is a warning: a red build for a
sentence of prose teaches people to bypass the gate.
"""

from .. import ids
from ..lints.base import rel
from ..segments import SEGMENTS_PATH, declared, load_segments
from ..violations import Violation
from .base import check


def _in_use(store) -> dict[str, list[str]]:
    """Segment name → the ids carrying it. Drafts have ULIDs and no segment."""
    out: dict[str, list[str]] = {}
    for ru in store.rus():
        try:
            segment, _ = ids.split(ru.id, "RU")
        except ValueError:
            continue                        # a draft: not a segmented id
        if segment:
            out.setdefault(segment, []).append(ru.id)
    return out


@check("C16")
def run(store):
    out = []
    where = rel(store, str(store.root.joinpath(*SEGMENTS_PATH)))
    known = declared(store.root)

    # The unrepairable violation comes FIRST. Everything below it is a typo in a
    # file the consumer is editing right now; this one says ids exist that name a
    # domain the store no longer declares, and ids are never rewritten. Reporting
    # it under four shape errors buries the only entry that cannot be undone.
    for segment, members in sorted(_in_use(store).items()):
        if segment in known:
            continue
        shown = ", ".join(sorted(members)[:4])
        out.append(Violation(
            rule="C16", severity="error", artifact=segment, path=where,
            message=(f"segment {segment} is not declared, but {len(members)} id(s) "
                     f"permanently carry it ({shown})."),
            suggestion="Restore the entry under its original name. A segment name is "
                       "permanent: it lives in filenames, gate stamps, review "
                       "directory names, packets and `verifies:` annotations in your "
                       "own source, and ids are never rewritten — so renaming or "
                       "removing one is a mass supersession, not an edit. To retire a "
                       "segment, set `closed: true`; its ids keep working (formats §1)."))

    seen: set[str] = set()
    for entry in load_segments(store.root):
        if not isinstance(entry, dict):
            out.append(Violation(
                rule="C16", severity="error", artifact=str(entry)[:40], path=where,
                message=f"segment entry {entry!r} is not a table.",
                suggestion="Each entry is a table with `name` and `domain` — a bare "
                           "string declares a name with no stated domain, which is "
                           "how a segment becomes the place undecided requirements "
                           "go (formats §1)."))
            continue
        name = str(entry.get("name") or "")
        if not name:
            out.append(Violation(
                rule="C16", severity="error", artifact="(unnamed)", path=where,
                message="a segment entry declares no `name`.",
                suggestion="Give it the name its ids carry, or remove the entry "
                           "(formats §1)."))
            continue
        if not ids.is_segment(name):
            out.append(Violation(
                rule="C16", severity="error", artifact=name, path=where,
                message=f"'{name}' is not a legal segment name.",
                suggestion="2-8 characters, uppercase, starting with a letter, and "
                           "never something the sequence alphabet can spell — "
                           "'CART' would make RU-CART ambiguous, while AUTH and ORDS "
                           "are fine because U and O are not in the alphabet "
                           "(formats §1)."))
        elif name in seen:
            out.append(Violation(
                rule="C16", severity="error", artifact=name, path=where,
                message=f"{name} is declared more than once.",
                suggestion="Keep one entry per segment — two make 'is this closed' "
                           "ambiguous the moment they disagree (formats §1)."))
        elif not str(entry.get("domain") or "").strip():
            # Warning, not error: nothing in the framework READS `domain`, and
            # what is mechanically checkable — a non-blank string — is satisfied
            # by `domain: TBD`. A store that declared its first segments at this
            # morning's sitting legitimately owes this sentence for an afternoon,
            # and a red build for prose teaches people to bypass the gate.
            out.append(Violation(
                rule="C16", severity="warning", artifact=name, path=where,
                message=f"{name} states no `domain`.",
                suggestion="Say in prose what this segment governs. The name is "
                           "permanent — a segment can be added and closed, never "
                           "renamed or merged — and a segment nobody can describe "
                           "is where requirements go when the reviewer could not "
                           "decide (formats §1)."))
        seen.add(name)

    return out
