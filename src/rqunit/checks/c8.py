"""C8 — every model vocabulary binding resolves to a manifest entry (spec
§10.2, §5.7: manifests own vocabulary, models own dynamics). Resolution runs
against the manifests reachable from the RUs that verify against the model
(their scope services + shared); a model no active RU references falls back
to all manifests (plan D-P3.5)."""

from ..errors import MalformedRef, UnresolvedRef
from ..lints.base import rel
from ..violations import Violation
from .base import check


@check("C8")
def run(store):
    out = []
    models = store.models()
    scopes_by_model: dict[str, set[str]] = {m: set() for m in models}
    for ru in store.rus():
        if ru.status != "active":
            continue
        for entry in ru.raw.get("verification") or []:
            if entry.get("type") == "model":
                bare = entry["ref"].removeprefix("MDL-")
                if bare in scopes_by_model:
                    scope = store.scope_service(ru)
                    if scope:
                        scopes_by_model[bare].add(scope)
    for model_id, model in models.items():
        scopes = scopes_by_model[model_id] or set(store.manifests())
        for event, token in (model.raw.get("vocabulary") or {}).items():
            if token == "internal":
                continue
            if not _resolves(store, token, scopes):
                out.append(Violation(
                    rule="C8", severity="error", artifact=f"MDL-{model_id}",
                    path=rel(store, model.path),
                    message=f"event {event} binds to {token}, which resolves in no reachable manifest "
                            f"(searched: {', '.join(sorted(scopes))}).",
                    suggestion="Declare the surface in the owning manifest — a model may not introduce "
                               "vocabulary (P8, §5.7)."))
    return out


def _resolves(store, token, scopes) -> bool:
    for scope in scopes:
        try:
            store.resolve_ref(token, scope)
            return True
        except (MalformedRef, UnresolvedRef):
            continue
    return False
