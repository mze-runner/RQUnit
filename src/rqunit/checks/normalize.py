"""C1 trigger/response normalizer — shipped as its own tested module (donor
TASK-040 note). Reference tokens flatten to their keys; content words are
lemmatized with a deliberately dumb suffix-stripper; the result is a SET, so
reorderings and passive voice collide while paraphrases (different words)
do not — the documented miss C1 accepts."""

from __future__ import annotations

import re

STOPWORDS = frozenset(
    "a an the is are was were be been being by for of to with that this those "
    "these it its their any every each via in on at as and or when while if "
    "then where shall system".split()
)

_TOKEN = re.compile(r"\{[a-z]+:([a-z0-9_./-]+)\}")
_WORD = re.compile(r"[a-z0-9_./-]+")


def lemma(word: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def content_words(text: str) -> frozenset[str]:
    text = _TOKEN.sub(r" \1 ", text.lower())
    return frozenset(
        lemma(w) for w in _WORD.findall(text) if w not in STOPWORDS
    )
