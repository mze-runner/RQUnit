"""L9 — identity hygiene (spec §10.1, §7.1). Filename↔id and id-format-per-
lifecycle are enforced structurally (store loader + schema); the residual lint
surface is the dangling-ULID scan: no non-draft RU may reference a draft ULID
anywhere in its file — activation rewrites all draft cross-references in the
same commit, so a leftover token means a botched or hand-rolled activation."""

import re

from ..violations import Violation
from .base import lint, rel

_DRAFT_TOKEN = re.compile(r"RU-draft-[0-9A-HJKMNP-TV-Z]{26}")


@lint("L9")
def run(store):
    out = []
    for ru in store.rus():
        if ru.status == "draft":
            continue
        # The `draft_id` provenance field legitimately carries the pre-activation
        # ULID (§7.1 "ULID kept as draft_id") — exempt exactly that line.
        text = "\n".join(
            line for line in ru.path.read_text().splitlines()
            if not line.startswith("draft_id:")
        )
        for token in sorted(set(_DRAFT_TOKEN.findall(text))):
            out.append(Violation(
                rule="L9", severity="error", artifact=ru.id, path=rel(store, ru.path),
                message=f"non-draft RU references draft ULID {token} — activation must rewrite "
                        "every draft cross-reference in its single commit (§7.1).",
                suggestion="Replace the ULID with the permanent RU-XXXX id assigned at Gate 1."))
    return out
