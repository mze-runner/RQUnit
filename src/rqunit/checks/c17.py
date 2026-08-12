"""C17 — every access tier a declared surface uses is bound to the credential
that admits it (spec §5.9, formats §16).

C5 validates tier membership on both sides and never relates them:
`endpoint.access` ∈ `access_tiers`, and separately `artifact.access_tier` ∈
`access_tiers`. So a store could declare a protected surface while nothing
described what protects it, two credentials could claim one tier, and every gate
stayed green — a door with no stated lock reads exactly like a door with one.

**Derived, never restated.** The tier string is the join: no `artifact:` key on
the endpoint. A direct reference would make the same fact expressible twice, and
`access: protected, artifact: jwt-pending-verification` becomes representable —
a contradiction the tier alone cannot express.

**Exactly one, and that is a claim about the consumer's model.** A tier admitting
two credential shapes cannot tell a test what to send, so the join would not be
total; if both are genuinely accepted they are two tiers. The escape valve for a
genuinely open surface is `credential_free_tiers`, which costs one line and is
itself worth having: a consumer whose surfaces admit unauthenticated requests has
now DECLARED that, where before it was indistinguishable from an oversight.

Scoped to tiers **in use by a declared surface**: a vocabulary may run ahead of
the surfaces that will use it, and demanding a credential for a tier nothing
serves yet would be enforcing target state.
"""

from ..lints.base import rel
from ..violations import Violation
from .base import check


@check("C17")
def run(store):
    manifests = store.manifests()
    shared = manifests.get("shared")
    if shared is None:
        return []                       # C5's error: no reachable tier vocabulary

    free = set(shared.raw.get("credential_free_tiers") or [])
    artifacts = shared.raw.get("artifacts") or {}
    where = rel(store, shared.path)

    # tier → the artifacts claiming it, and tier → the surfaces using it.
    claimed: dict[str, list[str]] = {}
    for artifact_id, artifact in artifacts.items():
        tier = artifact.get("access_tier")
        if tier:
            claimed.setdefault(tier, []).append(artifact_id)

    used: dict[str, list[str]] = {}
    for service, manifest in manifests.items():
        for section in ("endpoints", "channels"):
            for entry in manifest.raw.get(section) or []:
                used.setdefault(entry["access"], []).append(
                    f"{service}:{section}.{entry['id']}")

    out = []
    for tier in sorted(used):
        surfaces = used[tier]
        carriers = sorted(claimed.get(tier, []))
        if tier in free:
            if carriers:
                out.append(_v(where, tier,
                              f"tier '{tier}' is declared credential-free, yet "
                              f"{', '.join(carriers)} claims it.",
                              "A tier either requires a credential or it does not. Drop it "
                              "from `credential_free_tiers`, or move that artifact to the "
                              "tier it really describes."))
            continue
        if not carriers:
            out.append(_v(where, tier,
                          f"tier '{tier}' is used by {len(surfaces)} surface(s) and no "
                          "artifact declares it — the credential admitting these requests "
                          "is unmodelled.",
                          "Declare the credential under `artifacts` with "
                          f"`access_tier: {tier}` — `fields: none` is the honest census for "
                          "an opaque token, and naming it is what the binding needs. If "
                          "these surfaces genuinely admit unauthenticated requests, list "
                          f"'{tier}' in `credential_free_tiers` and the claim is on the "
                          "record."))
        elif len(carriers) > 1:
            out.append(_v(where, tier,
                          f"tier '{tier}' is claimed by {len(carriers)} artifacts "
                          f"({', '.join(carriers)}).",
                          "One tier, one credential shape — a tier admitting two cannot tell "
                          "a test what to send. If both are genuinely accepted, they are two "
                          "tiers."))
    return out


def _v(where: str, tier: str, message: str, suggestion: str) -> Violation:
    return Violation(rule="C17", severity="error", artifact=f"shared:access_tiers.{tier}",
                     path=where, message=message, suggestion=suggestion)
