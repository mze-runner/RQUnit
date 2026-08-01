"""C10 — every endpoint declares both directions of its surface (spec §5.9).

`inbound` and `outbound` are mandatory, and `none` is a legal, meaningful value:
it asserts the surface carries nothing that way, which an extractor can falsify.
An ABSENT slot asserts nothing. Distinguishing the two is the whole point of
making the declaration mandatory — a boundary silent about a direction reads
exactly like one that has none.

Not expressed as `required` in the schema on purpose: a schema rejection stops
the store parsing and yields one message saying only "invalid", where this
yields one attributable violation per endpoint carrying a fix.
"""

from ..lints.base import rel
from ..violations import Violation
from .base import check

_WHY = {
    "inbound": "what the endpoint accepts — path, query and body (§5.9)",
    "outbound": "the success response and its status (§5.9)",
}


@check("C10")
def run(store):
    out = []
    for service, manifest in store.manifests().items():
        for e in manifest.raw.get("endpoints") or []:
            for direction in ("inbound", "outbound"):
                if direction in e:
                    continue
                out.append(Violation(
                    rule="C10", severity="error",
                    artifact=f"{service}:endpoints.{e['id']}",
                    path=rel(store, manifest.path),
                    message=f"declares no `{direction}` — {_WHY[direction]}.",
                    suggestion=(
                        f"Declare `{direction}` on this endpoint. If it genuinely carries nothing, "
                        f"say so explicitly ({'inbound: none' if direction == 'inbound' else 'outbound: {status: 204, fields: none}'}) "
                        "— an omitted direction is unfinished work, a declared `none` is a claim (§5.9)."),
                ))
    return out
