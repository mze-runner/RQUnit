"""L16 — no shadowing: a service manifest key duplicating a shared key is an
error (spec §5.5) — resolution must stay unambiguous."""

from ..violations import Violation
from .base import lint, manifest_value_leaves, rel


def _key_sets(manifest_raw):
    return {
        "values": set(manifest_value_leaves(manifest_raw.get("values") or {})),
        "vocabularies": set((manifest_raw.get("vocabularies") or {})),
        "problem_types": set((manifest_raw.get("problem_types") or {})),
        "audit_events": {e["code"] for e in manifest_raw.get("audit_events") or []},
    }


@lint("L16")
def run(store):
    manifests = store.manifests()
    shared = manifests.get("shared")
    if shared is None:
        return []
    shared_keys = _key_sets(shared.raw)
    out = []
    for service, manifest in manifests.items():
        if service == "shared":
            continue
        for section, keys in _key_sets(manifest.raw).items():
            for key in sorted(keys & shared_keys[section]):
                out.append(Violation(
                    rule="L16", severity="error", artifact=service, path=rel(store, manifest.path),
                    message=f"{section} key '{key}' shadows shared.manifest.yaml — resolution must be "
                            "unambiguous (§5.5).",
                    suggestion="Delete the service copy (the shared fact wins), or rename it if it is "
                               "genuinely a different fact."))
    return out
