"""L11 — FEAT nodes carry no normative language (spec §2.1). The schema makes
verification/scope structurally impossible; this is the RFC-2119 keyword scan
of `goal`. Keyword set per plan D-P1.5: shall|must|should any case, MAY
uppercase-only (lowercase 'may' is unavoidable prose)."""

import re

from ..violations import Violation
from .base import lint, rel

_KEYWORDS = re.compile(r"\b(shall|must|should)\b", re.IGNORECASE)
_MAY = re.compile(r"\bMAY\b")


@lint("L11")
def run(store):
    out = []
    for feat in store.features():
        goal = feat.raw["goal"]
        hit = _KEYWORDS.search(goal) or _MAY.search(goal)
        if hit:
            out.append(Violation(
                rule="L11", severity="error", artifact=feat.id, path=rel(store, feat.path),
                message=f"FEAT goal contains normative keyword '{hit.group(0)}' — a FEAT is grouping "
                        "plus motivation, never a requirement (§2.1).",
                suggestion="Move the normative statement into an RU; restate the goal as motivation."))
    return out
