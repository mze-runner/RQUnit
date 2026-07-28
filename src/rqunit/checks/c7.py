"""C7 — orphan manifest facts: surfaces and SHARED values referenced by no
active RU → finding, never blocking ("dead interface or missing requirement;
a finding either way", spec §10.2). Plan D-P3.4: references count when they
appear as statement tokens of an active RU OR in the vocabulary of a model an
active RU verifies against (transitive governance). On a mid-migration store
this is the legacy burn-down list."""

from ..errors import MalformedRef, UnresolvedRef
from ..lints.base import manifest_value_leaves, rel
from ..parser.tokens import extract
from ..violations import Violation
from .base import check


@check("C7")
def run(store):
    referenced: set[tuple[str, str, str]] = set()  # (service, kind, key)
    model_refs: set[str] = set()
    for ru in store.rus():
        if ru.status != "active":
            continue
        scope = store.scope_service(ru)
        tokens, _ = extract(ru.raw["statement"])
        for t in tokens:
            try:
                r = store.resolve_ref(t.raw, scope)
                referenced.add((r.service, r.kind, r.key))
            except (MalformedRef, UnresolvedRef):
                continue  # L15's finding, not C7's
        for entry in ru.raw.get("verification") or []:
            if entry.get("type") == "model":
                model_refs.add(entry["ref"].removeprefix("MDL-"))
        for model_id in model_refs & set(store.models()):
            for token in store.models()[model_id].raw.get("vocabulary", {}).values():
                if token == "internal":
                    continue
                try:
                    r = store.resolve_ref(token, scope)
                    referenced.add((r.service, r.kind, r.key))
                except (MalformedRef, UnresolvedRef):
                    continue
    out = []
    for service, manifest in store.manifests().items():
        for kind, section in (("endpoint", "endpoints"), ("message", "messages"), ("channel", "channels")):
            for entry in manifest.raw.get(section) or []:
                if (service, kind, entry["id"]) not in referenced:
                    out.append(_finding(store, manifest, service,
                                        f"{section}.{entry['id']} is referenced by no active RU",
                                        entry.get("ru")))
        if service == "shared":
            for dotted in manifest_value_leaves(manifest.raw.get("values") or {}):
                if (service, "value", dotted) not in referenced:
                    out.append(_finding(store, manifest, service,
                                        f"shared value {dotted} is referenced by no active RU", None))
    return out


def _finding(store, manifest, service, what, bridge):
    via = f" (bridge link: {bridge})" if bridge else ""
    return Violation(
        rule="C7", severity="finding", artifact=service, path=rel(store, manifest.path),
        message=f"orphan fact: {what}{via} — dead interface or missing requirement.",
        suggestion="Compile the governing RU when this area migrates, or delete the fact at Gate 1.")
