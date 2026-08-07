"""L21 — coverage policy (spec §6.7): every RU satisfies the FIRST matching
rule in coverage.policy.yaml. Active violators → warning (burn-down after a
tightening, never a mass red build); draft violators → error (they cannot
activate under-covered — spec-activate enforces the blocking half too).
Policy is data; extending it is a PR to the policy file, never a lint change.

`binds_shape` (v0.14) is the one requirement that reads the STATEMENT rather
than `verification`. It exists because shape-binding moved: an RU used to prove
it was bound to a declared shape by carrying `verification: contract`, and now
it does so by addressing a field in its statement. Without this the policy could
still say "two mechanical checks" but had lost the ability to say "and it must
actually be bound to a declared shape" — a weaker guarantee wearing the same
name."""

from pathlib import Path

import yaml

from ..errors import MalformedRef, UnresolvedRef
from ..parser.tokens import extract
from ..violations import Violation
from .base import lint, rel

MECHANICAL = ("test", "model")

# Kinds whose referents carry a declared field census. A bare `{endpoint:id}`
# does NOT bind a shape — naming a surface is not describing what it carries —
# so an endpoint token must address a direction.
_CENSUS_KINDS = {"audit", "artifact"}


def binds_shape(store, ru) -> bool:
    """Does this statement address something with a declared census?"""
    tokens, _ = extract(ru.raw.get("statement") or "")
    scope = store.scope_service(ru)
    for token in tokens:
        if token.kind == "endpoint" and "." not in token.key:
            continue                      # names the surface, not its shape
        if token.kind not in _CENSUS_KINDS and token.kind != "endpoint":
            continue
        try:
            store.resolve_ref(token.raw, scope)
        except (MalformedRef, UnresolvedRef):
            continue                      # L15 owns unresolved refs; not this rule's business
        return True
    return False


def load_policy(store) -> dict | None:
    path = Path(store.root) / "spec" / "framework" / "coverage.policy.yaml"
    if not path.is_file():
        return None
    return yaml.safe_load(path.read_text())


def first_matching_rule(policy: dict, ru) -> dict:
    tags = set(ru.raw.get("tags") or [])
    for rule in policy.get("rules") or []:
        match = rule.get("match") or {}
        if "tier" in match and ru.tier != match["tier"]:
            continue
        if "tags_any" in match and not (tags & set(match["tags_any"])):
            continue
        return rule
    return policy.get("default") or {"require": {"min_verifications": 1}}


def violation_reason(rule: dict, entries: list, shape_bound: bool = True,
                     unshimmed: frozenset[str] = frozenset()) -> str | None:
    require = rule.get("require") or {}
    if require.get("binds_shape") and not shape_bound:
        return ("requires the statement to bind a declared shape — an {endpoint:<id>.<direction>"
                "[.<field>]}, {audit:<code>} or {artifact:<id>} reference. Naming a surface is "
                "not describing what it carries")
    # A model whose shim is unregistered contributes ZERO depth to every
    # requirement clause, not just the mechanical minimum: its suite is
    # rendered unrunnable, and a suite that cannot execute is not depth.
    # Counting it would let declared depth exceed provable depth — the same
    # overstatement removing `contract` from MECHANICAL fixed.
    def counts(entry: dict) -> bool:
        return not (entry.get("type") == "model"
                    and str(entry.get("ref", "")).removeprefix("MDL-") in unshimmed)

    types = [e.get("type") for e in entries if counts(e)]
    mechanical = [t for t in types if t in MECHANICAL]
    if "min_mechanical" in require and len(mechanical) < require["min_mechanical"]:
        pending = [str(e.get("ref")) for e in entries
                   if e.get("type") == "model"
                   and str(e.get("ref", "")).removeprefix("MDL-") in unshimmed]
        note = (f" ({', '.join(pending)} has no registered shim, so its generated "
                "suite cannot execute and counts as no depth — register it in "
                "spec/framework/shims.yaml when the shim lands)" if pending else "")
        return (f"requires ≥{require['min_mechanical']} mechanical verifications "
                f"(test|model), found {len(mechanical)} — human never satisfies a "
                f"mechanical minimum{note}")
    if "types_all" in require:
        missing = [t for t in require["types_all"] if t not in types]
        if missing:
            return f"requires ALL of [{', '.join(require['types_all'])}]; missing: {', '.join(missing)}"
    if "types_any" in require and not any(t in types for t in require["types_any"]):
        return f"requires at least one of [{', '.join(require['types_any'])}]"
    if "min_verifications" in require and len(entries) < require["min_verifications"]:
        return f"requires ≥{require['min_verifications']} verifications, found {len(entries)}"
    return None


@lint("L21")
def run(store):
    policy = load_policy(store)
    if policy is None:
        return []
    from ..shims import registered_models
    unshimmed = frozenset(set(store.models()) - registered_models(store.root))
    out = []
    for ru in store.rus():
        if ru.status not in ("active", "draft"):
            continue
        rule = first_matching_rule(policy, ru)
        needs_shape = (rule.get("require") or {}).get("binds_shape")
        reason = violation_reason(rule, ru.raw.get("verification") or [],
                                  shape_bound=binds_shape(store, ru) if needs_shape else True,
                                  unshimmed=unshimmed)
        if reason:
            severity = "warning" if ru.status == "active" else "error"
            out.append(Violation(
                rule="L21", severity=severity, artifact=ru.id, path=rel(store, ru.path),
                message=f"coverage policy violation ({ru.status}): {reason}.",
                suggestion="Add the missing verification depth, or change the policy by PR "
                           "(Gate-1-governed data, §6.7)."))
    return out
