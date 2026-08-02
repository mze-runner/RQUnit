"""C1 — two active RUs on the same trigger that actually CONTRADICT each other
(spec §10.2). Clause-bearing templates only; catches reorderings, documented to
miss paraphrases.

Until v0.14 the rule read "same trigger, different response → conflict", which
mistook DECOMPOSITION for disagreement. Sharing a trigger is the normal case,
not a smell: §2.1 says each acceptance criterion becomes exactly one RU, so a
dozen RUs hanging off one endpoint is what a well-decomposed feature looks
like. Cancelling an order records an audit entry AND halts fulfilment AND
notifies billing — three obligations, one trigger, no conflict anywhere.

What genuinely contradicts is narrower, and mechanically separable:

  identical response          -> duplicate                     (warning)
  differs only by a number    -> same obligation, two bounds    (error)
  differs only by `not`       -> one asserts what the other denies (error)
  differs lexically           -> decomposition                  (silent)

The bound case is the one the old rule caught only by accident, buried among
false positives — "halt within 5 seconds" against "halt within 30 seconds" is
a real disagreement about one obligation, and it was arriving in a pile of
noise that trains people to stop reading the rule.

Semantic contradictions with neither signal — "shall retry" against "shall
abandon" — are NOT caught. That extends the paraphrase miss this check already
documents; a set-of-words normalizer cannot see it, and pretending otherwise
would be worse than the gap.
"""

from collections import defaultdict

from ..lints.base import rel, safe_parse
from ..violations import Violation
from .base import check
from .normalize import content_words

_NEGATION = "not"


def _disagreement(first: frozenset, other: frozenset) -> tuple[str, str] | None:
    """(message fragment, suggestion) when two responses contradict, else None."""
    difference = first ^ other
    if not difference:
        return None                                  # duplicate: handled by the caller

    if difference == {_NEGATION}:
        return ("one asserts what the other denies",
                "Two RUs cannot both hold. Resolve via supersession (§10.2 C1) — or if the "
                "denial is conditional, its condition belongs in the trigger.")

    if all(word.replace(".", "", 1).isdigit() for word in difference):
        return (f"the same obligation carries two bounds ({', '.join(sorted(difference))})",
                "One obligation, one bound. Supersede the stale RU, or register the value in a "
                "manifest and reference it from both if they are genuinely different facts.")

    return None                                      # decomposition, not disagreement


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
                    suggestion="Retire one of the pair via supersession, or merge at Gate 1."))
                continue
            disagreement = _disagreement(first_resp, resp)
            if disagreement:
                reason, suggestion = disagreement
                out.append(Violation(
                    rule="C1", severity="error", artifact=ru.id, path=rel(store, ru.path),
                    message=f"conflicts with {first_ru.id}: {reason}.",
                    suggestion=suggestion))
    return out
