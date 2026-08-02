"""C6 — every declared side effect resolves to its own registry (spec §10.2).

A surface makes three different claims about what it produces, and they have
different audiences: `emits` is what a CALLER can be told, `audits` is evidence
nobody outside ever sees, `publishes` is what subscribers receive. They were one
list until v0.14, resolved by trying each registry in turn — which is ambiguous
the day a problem type and an audit code share a name, and which made the
audit-on-mutation question ("does this endpoint record anything?") a search
through a union rather than a lookup.

Also here because it is the same reconciliation: an audit census may not declare
a field the store forbids in every record.
"""

from ..lints.base import rel
from ..violations import Violation
from .base import check

# key -> (registry description, suggestion when it does not resolve)
_KEYS = {
    "emits": ("problem type",
              "Declare it in problem_types, or move it: an audit code belongs in `audits` "
              "and a message in `publishes` (§5.2)."),
    "audits": ("audit code",
               "Declare it in audit_events, or move it: a problem type belongs in `emits` "
               "(§5.2)."),
    "publishes": ("message",
                  "Declare the message in this manifest, or drop the claim — an endpoint "
                  "cannot publish a subject the service does not own (§5.2)."),
}


def _registry(manifest, key: str) -> set[str]:
    raw = manifest.raw
    if key == "emits":
        return set(raw.get("problem_types") or {})
    if key == "audits":
        return {e["code"] for e in raw.get("audit_events") or []}
    return {m["id"] for m in raw.get("messages") or []}


@check("C6")
def run(store):
    out = []
    shared = store.manifests().get("shared")
    forbidden = set((shared.raw.get("audit_forbidden") or []) if shared else [])

    for service, manifest in store.manifests().items():
        path = rel(store, manifest.path)
        registries = {key: _registry(manifest, key) for key in _KEYS}

        surfaces = [("endpoints", e) for e in manifest.raw.get("endpoints") or []]
        surfaces += [("messages", m) for m in manifest.raw.get("messages") or []]
        for section, entry in surfaces:
            for key, (registry_name, suggestion) in _KEYS.items():
                for declared in entry.get(key) or []:
                    if declared in registries[key]:
                        continue
                    where = _elsewhere(registries, key, declared)
                    out.append(Violation(
                        rule="C6", severity="error",
                        artifact=f"{service}:{section}.{entry['id']}", path=path,
                        message=(f"`{key}` names '{declared}', which is not a declared "
                                 f"{registry_name}"
                                 + (f" — it is {where}." if where else ".")),
                        suggestion=suggestion))

        # An audit record that promises to carry what the store forbids everywhere.
        for event in manifest.raw.get("audit_events") or []:
            fields = event.get("fields")
            for field in fields if isinstance(fields, list) else []:
                if field.get("name") in forbidden and field.get("presence") == "always":
                    out.append(Violation(
                        rule="C6", severity="error",
                        artifact=f"{service}:audit_events.{event['code']}", path=path,
                        message=(f"declares '{field['name']}' as always present, but the store "
                                 "forbids it in every audit record."),
                        suggestion=("Remove the field, or remove it from `audit_forbidden` in the "
                                    "shared manifest at Gate 1 — an evidence trail carrying "
                                    "credential material is the defect the list exists to "
                                    "prevent (§5.4).")))
    return out


def _elsewhere(registries: dict[str, set[str]], key: str, name: str) -> str | None:
    """Naming the registry it DID land in turns 'unknown id' into 'wrong key'."""
    for other, names in registries.items():
        if other != key and name in names:
            return {"emits": "a problem type", "audits": "an audit code",
                    "publishes": "a message"}[other]
    return None
