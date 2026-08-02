"""L2 — bounds are literal or {value:...} refs; vague quantifiers are errors
(spec §10.1, §3.1). Wordlist ships as data (vague_terms.yaml). Bound-ref
resolution is NOT re-checked here — L15 owns resolution (donor plan note).
Scanning covers authored PROSE only: reference-token spans are masked first
(v0.10.4) — {problem:too-many-requests} is a manifest identifier the author
referenced, not words they chose. Bare, un-braced identifiers stay scanned:
naming a fact in prose is the restatement the lints push against."""

import re

from ..violations import Violation
from .base import lint, load_wordlist, prose, rel, safe_parse

_WORDS = load_wordlist("vague_terms.yaml")


def _phrase_in(phrase: str, text: str) -> bool:
    return re.search(rf"\b{re.escape(phrase)}\b", text, re.IGNORECASE) is not None


@lint("L2")
def run(store):
    out = []
    for ru in store.rus():
        ast = safe_parse(ru)
        if ast is None:
            continue
        bound_prose = prose(ast.bound.text) if ast.bound else ""
        response_prose = prose(ast.response)
        if ast.bound and ast.bound.kind == "word":
            hit = next((p for p in _WORDS["bound_position"] if _phrase_in(p, bound_prose)), None)
            out.append(Violation(
                rule="L2", severity="error", artifact=ru.id, path=rel(store, ru.path),
                message=(f"Unbounded quantifier '{hit}' in statement bound position."
                         if hit else f"bound '{ast.bound.text}' is neither number+unit nor a {{value:...}} ref."),
                suggestion="State a literal bound or reference a manifest value: {value:...}.",
            ))
        for phrase in _WORDS["bound_position"] + _WORDS["quantity_position"]:
            if ast.bound and _phrase_in(phrase, bound_prose):
                continue  # already reported above
            if _phrase_in(phrase, response_prose):
                out.append(Violation(
                    rule="L2", severity="error", artifact=ru.id, path=rel(store, ru.path),
                    message=f"Vague quantifier '{phrase}' in response.",
                    suggestion="Quantify it: a literal bound/count or a {value:...} ref.",
                ))
    return out
