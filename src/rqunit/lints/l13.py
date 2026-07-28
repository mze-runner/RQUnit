"""L13 — constitutional tier hard cap: ≤15 active store-wide (spec §3.4).
The violation lists every member so the demotion decision has its menu."""

from ..violations import Violation
from .base import lint

CAP = 15


@lint("L13")
def run(store):
    members = [ru for ru in store.rus() if ru.tier == "constitutional" and ru.status == "active"]
    if len(members) <= CAP:
        return []
    return [Violation(
        rule="L13", severity="error", artifact="store",
        path="spec/ru",
        message=f"{len(members)} active constitutional RUs exceed the hard cap of {CAP}: "
                + ", ".join(ru.id for ru in members) + ".",
        suggestion="Demote at Gate 1 — constitutional tier is for system-wide invariants only (§3.4).")]
