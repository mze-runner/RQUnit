"""Reference tokenizer (TASK-010, formats §2 EBNF, v0.10 qualifier).

Malformed tokens are typed errors DISTINCT from unresolved references — L15
reports them as a separate class. The qualifier is forbidden for kind `value`
at the grammar level (foreign scalars promote to shared, §5.3); the §5.3
allow-list (surfaces + problem/audit only) is enforced semantically by L15.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

KINDS = ("value", "endpoint", "problem", "audit", "message", "channel", "frame", "vocab",
         "artifact")

# Arity of the dotted key per kind (formats §2): single ident for most,
# dotted for value/audit/endpoint, exactly channel.frame for frame.
_SINGLE = {"problem", "message", "channel", "vocab"}

# v0.10.2: key idents admit hyphens (RFC 7807-style problem keys, service
# slugs) — the qualifier/key split stays unambiguous because "/" delimits.
# The body regex only splits qualifier from key; which key shapes are LEGAL is
# decided per kind below, because the kinds no longer share one shape.
_BODY = re.compile(
    r"^(?:(?P<qualifier>[a-z][a-z0-9-]*)/)?"
    r"(?P<key>[A-Za-z][A-Za-z0-9_-]*(?:\.[A-Za-z][A-Za-z0-9_-]*)*)$"
)

# Every kind but `endpoint`: a dotted path of lowercase idents.
_KEY_LOWER = re.compile(r"^[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*)*$")

# v0.14 — an artifact key names the artifact, optionally one of its fields:
#     <id>[.<field>]
# Two segments at most: an artifact is a flat claim set, not a nested payload.
_KEY_ARTIFACT = re.compile(r"^[a-z][a-z0-9-]*(?:\.[A-Za-z][A-Za-z0-9_-]*)?$")

# v0.13 — an endpoint key addresses a surface, optionally one of its two
# directions, optionally a path INTO that direction's declared census:
#     <id>[.<direction>[.<field>[.<field>...]]]
# The direction set is closed BY THE GRAMMAR, so a misspelling is malformed
# rather than merely unresolved — the mistake is in the reference, not in the
# manifest. Field segments admit the naming-convention union, because
# `conventions.field_names` decides which convention is legal in a given store
# (C13) and the grammar must not pre-empt that. The id segment stays lowercase,
# matching manifest `$defs/ident`, so every surface id remains addressable.
_KEY_ENDPOINT = re.compile(
    r"^[a-z][a-z0-9_-]*"
    r"(?:\.(?:inbound|outbound)(?:\.[A-Za-z][A-Za-z0-9_-]*)*)?$"
)


@dataclass(frozen=True)
class Token:
    kind: str
    key: str
    qualifier: str | None
    raw: str
    start: int


@dataclass(frozen=True)
class TokenError:
    reason: str  # unknown-kind | empty-key | nesting | qualified-value | malformed
    raw: str
    start: int


def extract(text: str) -> tuple[list[Token], list[TokenError]]:
    """Scan statement text for reference tokens. `{{` and `}}` are literal
    braces and never open a token."""
    tokens: list[Token] = []
    errors: list[TokenError] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if text.startswith("{{", i) or text.startswith("}}", i):
            i += 2
            continue
        if ch != "{":
            i += 1
            continue
        close = text.find("}", i + 1)
        inner_open = text.find("{", i + 1)
        if inner_open != -1 and (close == -1 or inner_open < close):
            # nested token — consume through the outermost close we can find
            outer_close = text.find("}", close + 1) if close != -1 else -1
            end = (outer_close if outer_close != -1 else (close if close != -1 else n - 1)) + 1
            errors.append(TokenError("nesting", text[i:end], i))
            i = end
            continue
        if close == -1:
            errors.append(TokenError("malformed", text[i:], i))
            break
        raw = text[i:close + 1]
        errors_or_token = _parse_body(raw, i)
        (tokens if isinstance(errors_or_token, Token) else errors).append(errors_or_token)
        i = close + 1
    return tokens, errors


def _parse_body(raw: str, start: int) -> Token | TokenError:
    body = raw[1:-1]
    kind, sep, rest = body.partition(":")
    if not sep:
        return TokenError("malformed", raw, start)
    if kind not in KINDS:
        return TokenError("unknown-kind", raw, start)
    if not rest:
        return TokenError("empty-key", raw, start)
    m = _BODY.match(rest)
    if not m:
        return TokenError("malformed", raw, start)
    qualifier, key = m.group("qualifier"), m.group("key")
    if qualifier and kind == "value":
        return TokenError("qualified-value", raw, start)
    pattern = {"endpoint": _KEY_ENDPOINT, "artifact": _KEY_ARTIFACT}.get(kind, _KEY_LOWER)
    if not pattern.match(key):
        return TokenError("malformed", raw, start)
    parts = key.count(".") + 1
    if kind in _SINGLE and parts != 1:
        return TokenError("malformed", raw, start)
    if kind == "frame" and parts != 2:
        return TokenError("malformed", raw, start)
    return Token(kind=kind, key=key, qualifier=qualifier, raw=raw, start=start)


def parse_one(raw: str) -> Token | TokenError:
    """Parse ONE complete token string, braces included.

    The resolver calls this rather than carrying its own regex: two
    implementations of a grammar kept "in lockstep" by hand is a drift class,
    not a safeguard. One grammar, one implementation."""
    if not (raw.startswith("{") and raw.endswith("}") and len(raw) > 2):
        return TokenError("malformed", raw, 0)
    if "{" in raw[1:-1] or "}" in raw[1:-1]:
        return TokenError("nesting", raw, 0)
    return _parse_body(raw, 0)
