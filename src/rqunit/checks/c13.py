"""C13 — wire-visible names follow the store's declared conventions (§5.2).

The token grammar admits the union of the conventions on purpose, so that an
organisation's house standard — not the framework's taste — decides which is
legal here. That decision is `conventions` in the shared manifest; this check is
what makes it mechanical instead of remembered. An absent table means
unenforced, so nothing changes for a store that has not opted in.

Spec identifiers are out of scope: the schema fixes those, which is what keeps
every id addressable by a token.
"""

import re

from ..lints.base import rel
from ..violations import Violation
from .base import check

_PATTERNS = {
    "snake_case": re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$"),
    "camelCase": re.compile(r"^[a-z][a-zA-Z0-9]*$"),
    "kebab-case": re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$"),
    "PascalCase": re.compile(r"^[A-Z][a-zA-Z0-9]*$"),
}
_PLACEHOLDER = re.compile(r"^\{.*\}$")


def _conventions(store):
    shared = store.manifests().get("shared")
    return (shared.raw.get("conventions") or {}) if shared else {}


def _violation(store, manifest, artifact, name, convention, what):
    return Violation(
        rule="C13", severity="error", artifact=artifact, path=rel(store, manifest.path),
        message=f"{what} '{name}' does not follow the declared {convention} convention.",
        suggestion=(f"Rename it to {convention}, or change `conventions` in the shared manifest "
                    "if the house standard moved. The convention is declared once and applies "
                    "store-wide (§5.2)."))


@check("C13")
def run(store):
    conventions = _conventions(store)
    field_convention = conventions.get("field_names")
    path_convention = conventions.get("path_segments")
    out = []
    for service, manifest in store.manifests().items():
        for e in manifest.raw.get("endpoints") or []:
            where = f"{service}:endpoints.{e['id']}"
            if field_convention:
                pattern = _PATTERNS[field_convention]
                for direction in ("inbound", "outbound"):
                    slot = e.get(direction)
                    if not isinstance(slot, dict):
                        continue
                    fields = slot.get("fields")
                    # `fields: none` is a declaration, not a list — iterating the
                    # string would walk its characters.
                    for f in fields if isinstance(fields, list) else []:
                        name = f.get("name") or ""
                        # Each dotted segment is a wire name in its own right.
                        for segment in name.split("."):
                            if segment and not pattern.match(segment):
                                out.append(_violation(store, manifest, f"{where}.{direction}",
                                                      segment, field_convention, "field name"))
            if path_convention:
                pattern = _PATTERNS[path_convention]
                for segment in (e.get("path") or "").split("/"):
                    if segment and not _PLACEHOLDER.match(segment) and not pattern.match(segment):
                        out.append(_violation(store, manifest, where, segment,
                                              path_convention, "path segment"))
    return out
