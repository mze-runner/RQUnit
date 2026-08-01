"""Route-path normalization for manifest ↔ code matching (spec §5.6).

Frameworks spell placeholders differently — `{id}`, `:id`, `<id>`, `*rest` —
and the placeholder NAME is a local choice on each side. Matching raw strings
therefore reports a CF1/CF2 pair for every parameterized route: two loud
divergences describing one route that is in fact present and correct.

So identity is the path with placeholders reduced to position, and names are
reconciled separately — against the declared `in: path` fields (C12), which is
where a name has meaning. This lives in the core, not in adapters: an adapter
that normalized its own paths would be deciding what counts as the same route,
and that judgment must be identical for every language.
"""

from __future__ import annotations

import re

# `{id}` / `{id:uuid}` (axum, OpenAPI, Spring) · `:id` (Express, Rails, older
# axum) · `<id>` / `<int:id>` (Flask) · `*rest` / `{*rest}` (wildcards).
_BRACED = re.compile(r"\{[^{}/]*\}")
_ANGLED = re.compile(r"<[^<>/]*>")
_COLON = re.compile(r"(?<=/):[^/]+")
_STAR = re.compile(r"(?<=/)\*[^/]*")

_PLACEHOLDER = "{}"


def normalize(path: str) -> str:
    """Identity form: every placeholder becomes a positional `{}`.

    >>> normalize("/api/v1/orders/{order_id}/items/:item_id")
    '/api/v1/orders/{}/items/{}'
    """
    out = _BRACED.sub(_PLACEHOLDER, path)
    out = _ANGLED.sub(_PLACEHOLDER, out)
    out = _COLON.sub(_PLACEHOLDER, out)
    out = _STAR.sub(_PLACEHOLDER, out)
    return out.rstrip("/") or "/"


def placeholder_names(path: str) -> list[str]:
    """Declared placeholder names, in order, stripped of any type prefix or
    suffix (`<int:id>` and `{id:uuid}` both name `id`)."""
    names = []
    for segment in path.split("/"):
        if not segment:
            continue
        inner = None
        if segment.startswith("{") and segment.endswith("}"):
            inner = segment[1:-1].lstrip("*")
        elif segment.startswith("<") and segment.endswith(">"):
            inner = segment[1:-1]
        elif segment.startswith(":"):
            inner = segment[1:]
        elif segment.startswith("*"):
            inner = segment[1:]
        if inner is None:
            continue
        # `<int:id>` names id; `{id:uuid}` names id. The convention differs by
        # framework, so take the side that is not a known type prefix.
        if ":" in inner:
            left, right = inner.split(":", 1)
            inner = right if left in _TYPE_PREFIXES else left
        if inner:
            names.append(inner)
    return names


_TYPE_PREFIXES = {"int", "float", "path", "string", "str", "uuid", "slug"}
