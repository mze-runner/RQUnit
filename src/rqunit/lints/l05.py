"""L5 — verification non-empty; all non-TODO refs resolve (spec §10.1).
`model` refs must resolve to a store model; `test` resolution is spec-trace's
job — format only here. Contract refs were the third case until v0.14 retired
them: a shape is a manifest fact now, and an RU binds to one through a
statement token, which L15 resolves."""

from ..violations import Violation
from .base import lint, rel


@lint("L5")
def run(store):
    out = []
    models = store.models()
    for ru in store.rus():
        entries = ru.raw.get("verification") or []
        if not entries:  # schema stage backstop
            out.append(Violation(
                rule="L5", severity="error", artifact=ru.id, path=rel(store, ru.path),
                message="verification is empty — an RU without a verification hook is a preference (P2).",
                suggestion="Add at least one entry; use ref: TODO(<description>) if the check is missing (§6.5)."))
            continue
        for entry in entries:
            if entry["type"] == "model":
                bare = entry["ref"].removeprefix("MDL-")
                if bare not in models:
                    out.append(Violation(
                        rule="L5", severity="error", artifact=ru.id, path=rel(store, ru.path),
                        message=f"verification references {entry['ref']}, but no such model exists in spec/models/.",
                        suggestion=f"Add spec/models/{entry['ref']}.statechart.json or fix the ref."))
    return out
