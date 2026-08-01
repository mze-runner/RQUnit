"""L15 — every manifest reference in a statement resolves (spec §5.3 v0.10).
Three distinct failure classes, never conflated:
- malformed (tokenizer grammar, incl. qualified value refs),
- allow-list (qualified refs are surfaces + problem/audit only — vocab is a
  controlled value set, so a qualified vocab ref bypasses shared promotion),
- unresolved (well-formed, resolves to nothing; qualified refs NEVER fall
  back past the named manifest)."""

from ..errors import MalformedRef, UnresolvedRef
from ..parser.tokens import extract
from ..violations import Violation
from .base import lint, rel

_QUALIFIABLE = {"endpoint", "message", "channel", "frame", "problem", "audit"}


@lint("L15")
def run(store):
    out = []
    for ru in store.rus():
        tokens, errors = extract(ru.raw["statement"])
        for err in errors:
            out.append(Violation(
                rule="L15", severity="error", artifact=ru.id, path=rel(store, ru.path),
                message=f"malformed reference {err.raw!r} ({err.reason}).",
                suggestion="Reference grammar: {kind:key} or {kind:service/key} — formats.md §2."))
        scope = store.scope_service(ru)
        for token in tokens:
            if token.qualifier and token.kind not in _QUALIFIABLE:
                out.append(Violation(
                    rule="L15", severity="error", artifact=ru.id, path=rel(store, ru.path),
                    message=f"{token.raw}: cross-service references are permitted to surfaces and "
                            "problem/audit entries only (§5.3).",
                    suggestion="Promote the fact to shared.manifest.yaml (§5.5) and reference it unqualified."))
                continue
            try:
                store.resolve_ref(token.raw, scope)
            except MalformedRef as e:
                out.append(Violation(
                    rule="L15", severity="error", artifact=ru.id, path=rel(store, ru.path),
                    message=str(e), suggestion="Reference grammar: formats.md §2."))
            except UnresolvedRef:
                searched = token.qualifier or (f"{scope}, shared" if scope else "shared")
                shape = _shape_diagnosis(token)
                out.append(Violation(
                    rule="L15", severity="error", artifact=ru.id, path=rel(store, ru.path),
                    message=(shape[0] if shape else
                             f"{token.raw} does not resolve (searched: {searched}"
                             + ("" if not token.qualifier else " — qualified refs never fall back")
                             + ")."),
                    suggestion=(shape[1] if shape else
                                "Declare the fact in the owning manifest, or fix the key/qualifier.")))
    return out


def _shape_diagnosis(token) -> tuple[str, str] | None:
    """A sharper message for an unresolved endpoint SHAPE reference (§5.9).

    Deliberately not its own rule number: L15 already owns "every manifest
    reference resolves", and a field of a declared census is a manifest
    reference. Splitting one concept across two permanent numbers would make
    reports and consumer suppressions ambiguous for no added coverage — only
    the message needs to be more specific.
    """
    if token.kind != "endpoint":
        return None
    endpoint_id, _, path = token.key.partition(".")
    if not path:
        return None
    direction, _, field = path.partition(".")
    if not field:
        return (f"{token.raw}: endpoint '{endpoint_id}' declares no `{direction}`.",
                f"Declare `{direction}` on that endpoint — C10 requires both directions, and "
                "`none` is the way to say it carries nothing (§5.9).")
    return (f"{token.raw}: the `{direction}` shape of '{endpoint_id}' declares no field "
            f"'{field}'.",
            "Declare the field in that census, or fix the reference. A statement may only "
            "assert about fields the surface admits — otherwise the requirement outlives the "
            "shape it describes (§5.9).")
