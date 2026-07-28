"""C3 — one RU's must_not_touch intersecting another's owns → warning
(spec §10.2): the pair cannot be co-assigned without H1 blocking the work."""

from itertools import permutations

from ..lints.base import rel
from ..violations import Violation
from .base import check
from .c2 import _overlap


@check("C3")
def run(store):
    out = []
    actives = [ru for ru in store.rus() if ru.status == "active" and ru.raw.get("scope")]
    for x, y in permutations(actives, 2):
        forbidden = x.raw["scope"].get("must_not_touch") or []
        hits = [(f, o) for f in forbidden for o in y.raw["scope"]["owns"] if _overlap(f, o)]
        if hits:
            out.append(Violation(
                rule="C3", severity="warning", artifact=x.id, path=rel(store, x.path),
                message=f"must_not_touch ({hits[0][0]}) intersects {y.id}'s owns ({hits[0][1]}) — "
                        "co-assigning these RUs would make H1 block the work.",
                suggestion="Confirm the boundary at Gate 1, or narrow one of the globs."))
    return out
