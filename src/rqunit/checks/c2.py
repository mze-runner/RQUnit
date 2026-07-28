"""C2 — overlapping scope.owns across unrelated domains → warning at Gate 1
(spec §10.2). Unrelated = different features with disjoint tags (plan D-P3.2).

Aggregation (operator ruling, 2026-07-26): one warning per unordered FEATURE
pair, not per RU pair — with service-rooted owns globs every same-service RU
pair overlaps, so RU-pair granularity is O(n²) noise at volume; the feature is
Gate 1's attention unit."""

from collections import defaultdict
from itertools import combinations

from ..lints.base import rel
from ..violations import Violation
from .base import check


def _overlap(a: str, b: str) -> bool:
    return a == b or a.startswith(b.rstrip("/*") + "/") or b.startswith(a.rstrip("/*") + "/")


@check("C2")
def run(store):
    groups: dict[frozenset, list] = defaultdict(list)
    actives = [ru for ru in store.rus() if ru.status == "active" and ru.raw.get("scope")]
    for x, y in combinations(actives, 2):
        fx, fy = x.raw.get("feature"), y.raw.get("feature")
        if fx == fy:
            continue
        if set(x.raw.get("tags") or []) & set(y.raw.get("tags") or []):
            continue
        hits = [(a, b) for a in x.raw["scope"]["owns"] for b in y.raw["scope"]["owns"] if _overlap(a, b)]
        if hits:
            groups[frozenset((fx or "(no feature)", fy or "(no feature)"))].append((x, y, hits[0]))
    out = []
    for features, pairs in sorted(groups.items(), key=lambda kv: sorted(kv[0])):
        a, b = sorted(features)
        first_x, first_y, (glob_x, glob_y) = pairs[0]
        out.append(Violation(
            rule="C2", severity="warning", artifact=f"{a} × {b}",
            path=rel(store, first_x.path),
            message=f"owns overlap across unrelated features ({len(pairs)} RU pair(s), e.g. "
                    f"{first_x.id} '{glob_x}' ~ {first_y.id} '{glob_y}').",
            suggestion="Confirm at Gate 1: shared ownership intended between these features, "
                       "or one side's scope globs are too wide."))
    return out
