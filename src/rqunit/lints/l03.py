"""L3 — compound-statement detection (spec §10.1, plan D-P1.2). Operates on
the parsed response, never a bare regex for "and": a conjunct starting with a
lexicon verb is a second normative clause; object coordination is not.
Known miss: paraphrased second clauses with out-of-lexicon verbs — mitigated
by analyst dedupe (§8.1); extend verbs.yaml before extending code."""

from ..violations import Violation
from .base import lint, load_wordlist, rel, safe_parse

_VERBS = set(load_wordlist("verbs.yaml")["verbs"])


@lint("L3")
def run(store):
    out = []
    for ru in store.rus():
        ast = safe_parse(ru)
        if ast is None:
            continue
        reasons = []
        if ast.shall_clauses > 1:
            reasons.append(f"{ast.shall_clauses} coordinated shall-clauses")
        if "; " in ast.response:
            reasons.append("semicolon-joined clauses")
        for conjunct in ast.response.split(" and ")[1:]:
            first = conjunct.split(" ", 1)[0].rstrip(".,")
            if first in _VERBS:
                reasons.append(f"verb-initial conjunct 'and {first} ...'")
        for reason in reasons:
            out.append(Violation(
                rule="L3", severity="error", artifact=ru.id, path=rel(store, ru.path),
                message=f"compound statement: {reason}.",
                suggestion="Split into one RU per normative clause (one statement, one behaviour).",
            ))
    return out
