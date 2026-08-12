"""C15 — shim registrations name real models, once each (spec §6.3, §10.2).

A registration is a claim that a model's generated suite executes, and the
coverage policy reads it as depth. A claim naming a model the store does not
carry proves nothing about anything; a duplicate makes "is this registered"
ambiguous the moment the two entries disagree about who registered it and
when. Both are consistency questions BETWEEN artifacts, which is what makes
this a check rather than a lint.
"""

from ..lints.base import rel
from ..shims import SHIMS_PATH, load_shims
from ..violations import Violation
from .base import check


@check("C15")
def run(store):
    out = []
    path = str(store.root.joinpath(*SHIMS_PATH))
    where = rel(store, path)
    models = set(store.models())
    seen: set[str] = set()
    for entry in load_shims(store.root):
        if not isinstance(entry, dict):
            out.append(Violation(
                rule="C15", severity="error", artifact=str(entry)[:40], path=where,
                message=f"shim registration {entry!r} is not a table.",
                suggestion="Each entry is a table with `model` and the identity that "
                           "registered it — a bare string registers nothing, and "
                           "silently dropping it would leave you chasing a warning "
                           "about a shim you believe you registered (§6.3)."))
            continue
        raw = str(entry.get("model", ""))
        bare = raw.removeprefix("MDL-")
        if bare not in models:
            out.append(Violation(
                rule="C15", severity="error", artifact=raw or "(unnamed)", path=where,
                message=(f"shim registration names {raw or '(nothing)'}, which is not a "
                         "model in this store."),
                suggestion="Register a model the store carries, or remove the entry — a "
                           "shim for a model nobody declared proves nothing about "
                           "anything (§6.3)."))
        elif bare in seen:
            out.append(Violation(
                rule="C15", severity="error", artifact=raw, path=where,
                message=f"{raw} is registered more than once.",
                suggestion="Keep one registration per model — two entries make "
                           "'is this registered' ambiguous the moment they disagree "
                           "about who registered it and when (§6.3)."))
        else:
            seen.add(bare)
    return out
