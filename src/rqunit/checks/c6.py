"""C6 — every `emits` entry resolves to a declared problem_type or audit event
in the same manifest (spec §10.2)."""

from ..lints.base import rel
from ..violations import Violation
from .base import check


@check("C6")
def run(store):
    out = []
    for service, manifest in store.manifests().items():
        problems = set(manifest.raw.get("problem_types") or {})
        audits = {e["code"] for e in manifest.raw.get("audit_events") or []}
        for e in manifest.raw.get("endpoints") or []:
            for emitted in e.get("emits") or []:
                if emitted not in problems and emitted not in audits:
                    out.append(Violation(
                        rule="C6", severity="error", artifact=f"{service}:endpoints.{e['id']}",
                        path=rel(store, manifest.path),
                        message=f"emits '{emitted}', which is neither a declared problem_type nor an audit event.",
                        suggestion="Declare it in problem_types/audit_events, or fix the emits entry (C6)."))
    return out
