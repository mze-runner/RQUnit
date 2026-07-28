"""L6 — model_hash currency (spec §10.1, §6.3). A stale hash marks the RU
FAILING in the report, not just the file: green against a stale model is red.
Currency is claimed by active and draft RUs only — a superseded/retired RU's
hash is PROVENANCE (the model as reviewed then); checking it would red the
store forever after any model evolution (the GAP22 deadlock). The lawful
refresh path for actives is `spec-activate reaffirm`."""

from ..violations import Violation
from .base import lint, rel


@lint("L6")
def run(store):
    out = []
    models = store.models()
    for ru in store.rus():
        if ru.status in ("superseded", "retired"):
            continue
        for entry in ru.raw.get("verification") or []:
            if entry.get("type") != "model":
                continue
            model = models.get(entry["ref"].removeprefix("MDL-"))
            if model is None:
                continue  # dangling ref is L5's finding
            if entry["model_hash"] != model.content_hash:
                out.append(Violation(
                    rule="L6", severity="error", artifact=ru.id, path=rel(store, ru.path),
                    message=(f"model_hash for {entry['ref']} is stale — RU computes FAILING until "
                             f"conformance is regenerated (recorded {entry['model_hash'][:18]}…, "
                             f"current {model.content_hash[:18]}…)."),
                    suggestion="Regenerate conformance from the current model, then record the new hash."))
    return out
