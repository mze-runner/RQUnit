"""C1 — same normalized trigger, conflicting responses → error; identical
responses → duplicate warning (spec §10.2, plan D-P3.1). Clause-bearing
templates only; catches reorderings, documented to miss paraphrases."""

from collections import defaultdict

from ..lints.base import rel, safe_parse
from ..violations import Violation
from .base import check
from .normalize import content_words


@check("C1")
def run(store):
    groups = defaultdict(list)
    for ru in store.rus():
        if ru.status != "active":
            continue
        ast = safe_parse(ru)
        if ast is None or not ast.clause:
            continue
        groups[(ast.template, content_words(ast.clause))].append((ru, content_words(ast.response)))
    out = []
    for members in groups.values():
        if len(members) < 2:
            continue
        first_ru, first_resp = members[0]
        for ru, resp in members[1:]:
            if resp == first_resp:
                out.append(Violation(
                    rule="C1", severity="warning", artifact=ru.id, path=rel(store, ru.path),
                    message=f"duplicate of {first_ru.id}: same normalized trigger AND response.",
                    suggestion=f"Retire one of the pair via supersession, or merge at Gate 1."))
            else:
                out.append(Violation(
                    rule="C1", severity="error", artifact=ru.id, path=rel(store, ru.path),
                    message=f"conflicts with {first_ru.id}: same normalized trigger, different response.",
                    suggestion="Two behaviours for one trigger — resolve via supersession (§10.2 C1)."))
    return out
