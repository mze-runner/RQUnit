"""L20 — suspect links (spec §7.3): every link_fingerprints entry must match
the current fingerprint of its target. A mismatch is NOT a red build — the
RU's checks may still pass — it is a finding that enters the suspect queue for
the next Gate 1 sitting (re-affirm or supersede; resolution is binary)."""

from ..canonical import link_fingerprint
from ..violations import Violation
from .base import lint, rel


@lint("L20")
def run(store):
    out = []
    for ru in store.rus():
        for target, recorded in (ru.raw.get("link_fingerprints") or {}).items():
            current = link_fingerprint(store, target)
            if current is None:
                message = f"fingerprinted target {target} no longer exists."
            elif current != recorded:
                message = f"target {target} changed after this RU relied on it."
            else:
                continue
            out.append(Violation(
                rule="L20", severity="finding", artifact=ru.id, path=rel(store, ru.path),
                message=f"suspect link: {message}",
                suggestion="Queue for the next Gate 1 sitting: re-affirm (refresh the fingerprint under "
                           "the reviewer's id) or supersede this RU (§7.3)."))
    return out
