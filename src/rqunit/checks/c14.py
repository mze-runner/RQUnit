"""C14 — a state-changing surface that records nothing (spec §5.4).

RU-0002, audit-on-mutation, is one of three constitutional invariants seeded into
every context assembly, and until now nothing checked it. This is its checkable
form: an endpoint whose method changes state and whose `audits` is empty.

`finding`, deliberately. HTTP method is a HEURISTIC for mutation — `POST /search`
and `POST /orders/preview` are routine and mutate nothing. At error severity this
would false-positive on ordinary designs and teach people to route around the
gate, which costs more than the rule earns. It reports; a human judges.
"""

from ..lints.base import rel
from ..violations import Violation
from .base import check

_MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


@check("C14")
def run(store):
    out = []
    for service, manifest in store.manifests().items():
        for endpoint in manifest.raw.get("endpoints") or []:
            if endpoint.get("method") not in _MUTATING or endpoint.get("planned"):
                continue
            if endpoint.get("audits"):
                continue
            out.append(Violation(
                rule="C14", severity="finding",
                artifact=f"{service}:endpoints.{endpoint['id']}",
                path=rel(store, manifest.path),
                message=(f"{endpoint['method']} {endpoint['path']} records no audit event — "
                         "a state-changing surface with no evidence trail."),
                suggestion=("Declare what it records in `audits`, or confirm the method is not "
                            "state-changing (a search over POST is ordinary). Constitutional "
                            "RU-0002 requires an audit event for every state-changing action; "
                            "this is a finding because the method is a heuristic, not proof.")))
    return out
