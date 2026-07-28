"""L10 — tags belong to the controlled vocabulary (spec §10.1, tags.yaml)."""

from ..violations import Violation
from .base import lint, rel


@lint("L10")
def run(store):
    out = []
    known = set(store.tags())
    for ru in store.rus():
        for tag in ru.raw.get("tags") or []:
            if tag not in known:
                out.append(Violation(
                    rule="L10", severity="error", artifact=ru.id, path=rel(store, ru.path),
                    message=f"tag '{tag}' is not in the controlled vocabulary (spec/framework/tags.yaml).",
                    suggestion=f"Add '{tag}' to tags.yaml in the same change (Gate 1 confirms new tags), "
                               "or use an existing tag — synonyms fragment ranking (§14)."))
    return out
