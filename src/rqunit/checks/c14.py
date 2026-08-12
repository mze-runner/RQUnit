"""C14 — a state-changing surface that records nothing (spec §5.4).

Audit-on-mutation is one of the constitutional invariants a store is expected to
seed, and until now nothing checked it. This is its checkable form: an endpoint
whose method changes state and whose `audits` is empty.

The MESSAGE states the invariant and never cites an id. `RU-0002` is the id
audit-on-mutation carries in this repository's own reference fixtures, and
`rqunit init` seeds no RUs — so citing it named an artifact that exists in no
consumer store, and would become actively false the day a consumer minted that
id for something else. It is the mirror image of the leakage rule this codebase
enforces on itself: no consumer's vocabulary may appear in the product, and the
product's fixture identity must not appear in a consumer's output.

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
                            "state-changing (a search over POST is ordinary). A state-changing "
                            "surface with no declared audit event has no evidence trail — the "
                            "constitutional invariant this makes checkable. A finding rather "
                            "than an error because the method is a heuristic, not proof.")))
    return out
