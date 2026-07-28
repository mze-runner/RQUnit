"""C5 — vocabulary membership (spec §10.2, plan D-P3.3): endpoint/channel
`access` values must belong to the shared `access_tiers` vocabulary (the tier
set is project data, not a schema enum — formats §8). Surfaces existing with
no reachable access_tiers vocabulary is itself the error.
v0.11 extends the same membership discipline to the contract layer: endpoint
`scope` values ∈ the `token_scopes` vocabulary (shared or the owning
service's); a contract's `access_tier` ∈ access_tiers; a contract field's
`vocab` names an existing manifest vocabulary; contract field names unique."""

from ..lints.base import rel
from ..violations import Violation
from .base import check


@check("C5")
def run(store):
    out = []
    manifests = store.manifests()
    shared = manifests.get("shared")
    tiers = set((shared.raw.get("vocabularies") or {}).get("access_tiers") or []) if shared else set()

    def scopes_for(service: str) -> set[str]:
        names: set[str] = set()
        for m in (manifests.get(service), shared):
            if m is not None:
                names |= set((m.raw.get("vocabularies") or {}).get("token_scopes") or [])
        return names

    for service, manifest in manifests.items():
        entries = [("endpoints", e) for e in manifest.raw.get("endpoints") or []] + \
                  [("channels", c) for c in manifest.raw.get("channels") or []]
        if entries and not tiers:
            out.append(Violation(
                rule="C5", severity="error", artifact=service, path=rel(store, manifest.path),
                message="surfaces declare access tiers but no shared `access_tiers` vocabulary exists.",
                suggestion="Seed vocabularies.access_tiers in spec/manifests/shared.manifest.yaml (formats §8)."))
            break
        for section, entry in entries:
            if entry["access"] not in tiers:
                out.append(Violation(
                    rule="C5", severity="error", artifact=f"{service}:{section}.{entry['id']}",
                    path=rel(store, manifest.path),
                    message=f"access tier '{entry['access']}' is not in the shared access_tiers vocabulary "
                            f"({', '.join(sorted(tiers))}).",
                    suggestion="Use a declared tier, or extend the vocabulary at Gate 1 (C5)."))
            scope = entry.get("scope")
            if scope is not None and scope not in scopes_for(service):
                out.append(Violation(
                    rule="C5", severity="error", artifact=f"{service}:{section}.{entry['id']}",
                    path=rel(store, manifest.path),
                    message=f"scope '{scope}' is not in a reachable `token_scopes` vocabulary "
                            f"(searched: {service}, shared).",
                    suggestion="Register the scope in vocabularies.token_scopes (shared or the "
                               "owning manifest) at Gate 1."))

    all_vocabs = {name for m in manifests.values()
                  for name in (m.raw.get("vocabularies") or {})}
    for ct_id, ct in store.contracts().items():
        tier = ct.raw.get("access_tier")
        if tier is not None and tier not in tiers:
            out.append(Violation(
                rule="C5", severity="error", artifact=ct_id, path=rel(store, ct.path),
                message=f"access_tier '{tier}' is not in the shared access_tiers vocabulary "
                        f"({', '.join(sorted(tiers))}).",
                suggestion="Bind the contract to a declared tier, or extend the vocabulary at Gate 1."))
        seen: set[str] = set()
        for field in ct.raw.get("fields") or []:
            if field["name"] in seen:
                out.append(Violation(
                    rule="C5", severity="error", artifact=ct_id, path=rel(store, ct.path),
                    message=f"field '{field['name']}' is declared twice — one field, one presence rule.",
                    suggestion="Collapse the duplicates; a field appearing 'sometimes' belongs to a "
                               "different artifact type with its own contract."))
            seen.add(field["name"])
            vocab = field.get("vocab")
            if vocab is not None and vocab not in all_vocabs:
                out.append(Violation(
                    rule="C5", severity="error", artifact=ct_id, path=rel(store, ct.path),
                    message=f"field '{field['name']}' binds values to vocabulary '{vocab}', "
                            "which exists in no manifest.",
                    suggestion="Declare the vocabulary in a manifest — contracts constrain values "
                               "through manifests, never introduce vocabulary (§5.7 spirit)."))
    return out
