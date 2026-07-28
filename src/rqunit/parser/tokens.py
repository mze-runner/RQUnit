"""Reference tokenizer (TASK-010, formats §2 EBNF, v0.10 qualifier).

Malformed tokens are typed errors DISTINCT from unresolved references — L15
reports them as a separate class. The qualifier is forbidden for kind `value`
at the grammar level (foreign scalars promote to shared, §5.3); the §5.3
allow-list (surfaces + problem/audit only) is enforced semantically by L15.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

KINDS = ("value", "endpoint", "problem", "audit", "message", "channel", "frame", "vocab")

# Arity of the dotted key per kind (formats §2): single ident for most,
# dotted for value/audit, exactly channel.frame for frame.
_SINGLE = {"endpoint", "problem", "message", "channel", "vocab"}

# v0.10.2: key idents admit hyphens (RFC 7807-style problem keys, service
# slugs) — the qualifier/key split stays unambiguous because "/" delimits.
_BODY = re.compile(
    r"^(?:(?P<qualifier>[a-z][a-z0-9-]*)/)?"
    r"(?P<key>[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*)*)$"
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
    parts = key.count(".") + 1
    if kind in _SINGLE and parts != 1:
        return TokenError("malformed", raw, start)
    if kind == "frame" and parts != 2:
        return TokenError("malformed", raw, start)
    return Token(kind=kind, key=key, qualifier=qualifier, raw=raw, start=start)
