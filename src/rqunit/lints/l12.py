"""L12 — the parsed EARS actor is a canonical registry id (spec §3.3).

v1 heuristic (pinned by the golden suite + plan): the clause subject is judged
only when it is (a) a registered alias — error with the canonical rename — or
(b) hyphenated-multiword and unknown — role names are hyphenated by
convention, bare nouns ("order", "user"?) are checked only against aliases.
Registered canonical ids always pass; manifest service names and 'system' are
never actors-in-error (a service can be a trigger subject)."""

from ..violations import Violation
from .base import lint, rel, safe_parse


@lint("L12")
def run(store):
    out = []
    actors = store.actors()
    services = set(store.manifests())
    for ru in store.rus():
        ast = safe_parse(ru)
        if ast is None or not ast.subject:
            continue
        subject = ast.subject
        if subject in actors or subject in services or subject == "system":
            continue
        canonical = store.alias_of(subject)
        if canonical:
            out.append(Violation(
                rule="L12", severity="error", artifact=ru.id, path=rel(store, ru.path),
                message=f"'{subject}' is an alias, not a canonical actor id.",
                suggestion=f"Rename to '{canonical}' (aliases are never valid in statements, §3.3)."))
        elif "-" in subject:
            out.append(Violation(
                rule="L12", severity="error", artifact=ru.id, path=rel(store, ru.path),
                message=f"actor '{subject}' is not in the registry (spec/framework/actors.yaml).",
                suggestion="Register the actor first (new actors enter the registry before statements use them), "
                           "or fix the spelling."))
    return out
