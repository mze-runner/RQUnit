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

    # An audit field constrained to a vocabulary — a `reason` drawn from a
    # controlled set — is the same membership claim a surface field makes, so it
    # is checked in the same place.
    for service, manifest in manifests.items():
        for event in manifest.raw.get("audit_events") or []:
            fields = event.get("fields")
            for field in fields if isinstance(fields, list) else []:
                vocab = field.get("vocab")
                if vocab is not None and vocab not in all_vocabs:
                    out.append(Violation(
                        rule="C5", severity="error",
                        artifact=f"{service}:audit_events.{event['code']}",
                        path=rel(store, manifest.path),
                        message=f"field '{field.get('name')}' constrains its values to "
                                f"'{vocab}', which is no declared vocabulary.",
                        suggestion="Declare the vocabulary in this manifest or shared — an audit "
                                   "record never introduces vocabulary (§5.7)."))
    declared_artifacts = set((shared_raw.get("artifacts") or {}) if (shared_raw := (
        manifests["shared"].raw if "shared" in manifests else {})) else {})
    for service, manifest in manifests.items():
        for endpoint in manifest.raw.get("endpoints") or []:
            for direction in ("inbound", "outbound"):
                slot = endpoint.get(direction)
                fields = slot.get("fields") if isinstance(slot, dict) else None
                for field in fields if isinstance(fields, list) else []:
                    ref = field.get("artifact")
                    if ref is not None and ref not in declared_artifacts:
                        out.append(Violation(
                            rule="C5", severity="error",
                            artifact=f"{service}:endpoints.{endpoint['id']}.{direction}",
                            path=rel(store, manifest.path),
                            message=f"field '{field.get('name')}' carries artifact '{ref}', "
                                    "which no shared manifest declares.",
                            suggestion="Declare it under `artifacts` in the shared manifest, or "
                                       "fix the reference — a field cannot carry a structure "
                                       "nothing describes (§5.9)."))

    # Shared artifacts: the tier binding is finally correct here — this is the
    # population "surfaces of this tier consume artifacts of this shape" always
    # described, once the layer stopped holding response bodies too.
    shared = manifests.get("shared")
    for artifact_id, artifact in ((shared.raw.get("artifacts") or {}).items() if shared else ()):
        where = f"shared:artifacts.{artifact_id}"
        tier = artifact.get("access_tier")
        if tier is not None and tier not in tiers:
            out.append(Violation(
                rule="C5", severity="error", artifact=where, path=rel(store, shared.path),
                message=f"access_tier '{tier}' is not in the shared access_tiers vocabulary "
                        f"({', '.join(sorted(tiers))}).",
                suggestion="Bind the artifact to a declared tier, or extend the vocabulary at "
                           "Gate 1."))
        for field in artifact.get("fields") or []:
            vocab = field.get("vocab")
            if vocab is not None and vocab not in all_vocabs:
                out.append(Violation(
                    rule="C5", severity="error", artifact=where, path=rel(store, shared.path),
                    message=f"field '{field.get('name')}' binds values to vocabulary '{vocab}', "
                            "which exists in no manifest.",
                    suggestion="Declare the vocabulary in a manifest — an artifact constrains "
                               "values through manifests, it never introduces them (§5.7)."))
    return out
