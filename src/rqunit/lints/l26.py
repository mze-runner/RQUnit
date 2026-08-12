"""L26 — a check that has never been observed failing (spec §6.8).

The defect this exists for: an agent that has read the implementation writes a
test asserting that implementation's shape. It is green from the first run,
it will stay green through any change that keeps the shape, and nothing in
the store can tell it from a check that earns its green. What separates them
is history — a check that has *ever* failed has demonstrated it can.

`finding`, and deliberately never `error`. A check may legitimately never have
been observed red (it was written first, and the ledger only starts when
recording starts), and blocking that case would reward theatrical failures:
break it once, record the red, restore it. The report is the point.

Scoped to `test` refs only. A `model` suite is generated from the statechart
and cannot be shaped by the implementation it checks, so the failure mode does
not apply to it.
"""

from ..evidence import never_red
from ..violations import Violation
from .base import lint, rel


@lint("L26")
def run(store):
    green_only = never_red(store.root)
    if not green_only:
        return []
    out = []
    for ru in store.rus():
        if ru.status not in ("active", "draft"):
            continue
        for entry in ru.raw.get("verification") or []:
            ref = str(entry.get("ref", ""))
            if entry.get("type") != "test" or ref not in green_only:
                continue
            out.append(Violation(
                rule="L26", severity="finding", artifact=ru.id, path=rel(store, ru.path),
                message=(f"check '{ref}' has passed and has never been observed "
                         "failing — it has not demonstrated that it can."),
                suggestion="Confirm it discriminates: break what it verifies and watch "
                           "it go red, then record that run (`rqunit evidence record`). "
                           "A check written against an implementation it had already "
                           "read can assert that implementation's shape and never fail "
                           "(§6.8)."))
    return out
