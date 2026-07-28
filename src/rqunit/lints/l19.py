"""L19 — every active RU carries a gate1_stamp matching the current canonical
serialization of its normative fields (spec §7.2). A mismatch means the RU was
edited after review — forbidden in-place mutation or tool error; both blocking.
The §7 freeze is thereby a mechanical check, not a convention."""

from ..canonical import canonical_hash
from ..violations import Violation
from .base import lint, rel


@lint("L19")
def run(store):
    out = []
    for ru in store.rus():
        if ru.status != "active":
            continue
        stamp = ru.raw.get("gate1_stamp")
        if not stamp:
            out.append(Violation(
                rule="L19", severity="error", artifact=ru.id, path=rel(store, ru.path),
                message="active RU carries no gate1_stamp — 'reviewed' must be computed, not asserted (§7.2).",
                suggestion="Stamp via `spec-activate restamp --reviewer <id>` after a Gate 1 sitting."))
        elif stamp.get("hash") != canonical_hash(ru.raw):
            out.append(Violation(
                rule="L19", severity="error", artifact=ru.id, path=rel(store, ru.path),
                message="gate1_stamp hash does not match the current normative fields — the statement/"
                        "scope/verification/tier changed AFTER review.",
                suggestion="Change = supersession (new RU + supersedes link), never in-place editing (§7)."))
    return out
