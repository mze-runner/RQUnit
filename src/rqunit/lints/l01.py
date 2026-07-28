"""L1 — statement parses under its declared syntax (spec §10.1)."""

from ..parser.ears import EarsParseError, parse
from ..violations import Violation
from .base import lint, rel


@lint("L1")
def run(store):
    out = []
    for ru in store.rus():
        try:
            parse(ru.raw["statement"], ru.raw.get("syntax", "ears"))
        except EarsParseError as e:
            d = e.diagnosis
            out.append(Violation(
                rule="L1", severity="error", artifact=ru.id, path=rel(store, ru.path),
                message=f"statement does not parse ({d.failed_slot}): {d.message}",
                suggestion=f"nearest template: {d.nearest_template} — see formats.md §3",
            ))
    return out
