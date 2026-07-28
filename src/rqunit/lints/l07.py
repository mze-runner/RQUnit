"""L7 — cross-artifact link integrity: supersession chains are acyclic;
superseded targets are not retired (spec §10.1, §7). Dangling link targets —
`supersedes` RUs and `rationale_ref` ADRs — are reported here too."""

from ..violations import Violation
from .base import lint, rel


@lint("L7")
def run(store):
    out = []
    by_id = {ru.id: ru for ru in store.rus()}
    for ru in store.rus():
        adr = ru.raw.get("rationale_ref")
        if adr and store.adr_path(adr) is None:
            out.append(Violation(
                rule="L7", severity="error", artifact=ru.id, path=rel(store, ru.path),
                message=f"rationale_ref {adr} does not resolve — no spec/rationale/{adr}.md in the store.",
                suggestion="Add the decision record under spec/rationale/ (format: formats §10) or drop the ref."))
        target_id = ru.raw.get("supersedes")
        if not target_id:
            continue
        target = by_id.get(target_id)
        if target is None:
            out.append(_v(store, ru, f"supersedes {target_id}, which does not exist"))
            continue
        if target.status == "retired":
            out.append(_v(store, ru, f"supersedes {target_id}, which is retired — "
                                     "retirement means the intent was withdrawn, not replaced"))
        seen = {ru.id}
        node = target
        while node is not None:
            if node.id in seen:
                out.append(_v(store, ru, f"supersession chain through {node.id} is cyclic"))
                break
            seen.add(node.id)
            node = by_id.get(node.raw.get("supersedes") or "")
    return out


def _v(store, ru, message):
    return Violation(rule="L7", severity="error", artifact=ru.id, path=rel(store, ru.path),
                     message=message + ".",
                     suggestion="Supersession replaces an active RU with a successor; chains must be acyclic (§3.1).")
