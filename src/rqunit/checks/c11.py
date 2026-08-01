"""C11 — declared shapes are well-formed (spec §5.9).

The schema deliberately admits the union of both presence vocabularies and every
bound key on every type, so that a mistake arrives as a message that teaches
rather than as a parse failure. This check is where that judgment lives.

The load-bearing one is presence: `never` outbound means MUST NOT LEAK, while
`forbidden` inbound means MUST BE REJECTED. They are different assertions with
different tests and different bug classes, so cross-wiring them is an error
rather than a nicety.
"""

from ..lints.base import rel
from ..violations import Violation
from .base import check

_PRESENCE = {
    "outbound": {"always", "never"},
    "inbound": {"required", "optional", "forbidden"},
}
_NEGATIVE = {"never", "forbidden"}
_BOUNDS = {
    "max_chars": {"string"}, "min_chars": {"string"},
    "min": {"integer", "number"}, "max": {"integer", "number"},
    "min_items": {"array"}, "max_items": {"array"},
}


def _fields(slot):
    """The declared field list, or [] when the direction carries nothing."""
    if not isinstance(slot, dict):
        return []
    fields = slot.get("fields")
    return fields if isinstance(fields, list) else []


@check("C11")
def run(store):
    out = []
    for service, manifest in store.manifests().items():
        default_policy = (manifest.raw.get("defaults") or {}).get("unknown_fields")
        for e in manifest.raw.get("endpoints") or []:
            for direction in ("inbound", "outbound"):
                slot = e.get(direction)
                where = f"{service}:endpoints.{e['id']}.{direction}"
                path = rel(store, manifest.path)

                def bad(message, suggestion):
                    out.append(Violation(rule="C11", severity="error", artifact=where,
                                         path=path, message=message, suggestion=suggestion))

                if direction == "inbound" and isinstance(slot, dict):
                    if slot.get("unknown_fields") is None and default_policy is None:
                        bad("no unknown-field policy resolves for this inbound shape.",
                            "Set `defaults.unknown_fields` for the service or `unknown_fields` on "
                            "this shape. There is no implicit value: what happens to an undeclared "
                            "field is itself a requirement (§5.9).")

                fields = _fields(slot)
                names = [f.get("name") for f in fields]
                declared = set(names)
                for name in {n for n in names if names.count(n) > 1}:
                    bad(f"field '{name}' is declared more than once.",
                        "One declaration per field — two rows for one name make the census "
                        "ambiguous about which claim holds (§5.9).")

                for f in fields:
                    name, presence = f.get("name"), f.get("presence")
                    if presence not in _PRESENCE[direction]:
                        other = "outbound" if direction == "inbound" else "inbound"
                        bad(f"field '{name}' uses presence '{presence}', which belongs to "
                            f"{other} shapes.",
                            f"Use one of {sorted(_PRESENCE[direction])} here. Outbound `never` "
                            "means must-not-leak; inbound `forbidden` means must-be-rejected — "
                            "different claims, different tests (§5.9).")
                    if direction == "outbound" and f.get("in"):
                        bad(f"field '{name}' declares `in: {f['in']}`, which describes where a "
                            "CLIENT supplies a value.",
                            "Drop `in` from outbound fields — it is meaningful on inbound only (§5.9).")
                    if f.get("nullable") is not None and presence in _NEGATIVE:
                        bad(f"field '{name}' is '{presence}' yet declares `nullable`.",
                            "Drop `nullable`: presence is about the KEY, nullable about the VALUE, "
                            "and a field that never appears has no value to be null (§5.9).")
                    if f.get("type") == "array" and not f.get("items"):
                        bad(f"array field '{name}' declares no `items`.",
                            "Name the element type with `items:` — an array of unstated elements "
                            "constrains nothing (§5.9).")
                    if f.get("type") == "object" and not any(
                            n and n.startswith(f"{name}.") for n in names):
                        bad(f"object field '{name}' declares no members.",
                            f"Declare its members as dotted children ('{name}.<field>'). An object "
                            "with no declared members is an unbounded blob that reads as "
                            "specified (§5.9).")
                    for key, types in _BOUNDS.items():
                        if f.get(key) is not None and f.get("type") not in types:
                            bad(f"field '{name}' declares `{key}` but is typed "
                                f"'{f.get('type') or 'unspecified'}'.",
                                f"`{key}` applies to {sorted(types)} only — fix the type or drop "
                                "the bound (§5.9).")
                    if name and "." in name:
                        parent = name.rsplit(".", 1)[0]
                        if parent not in declared:
                            bad(f"field '{name}' declares a member of '{parent}', which is not "
                                "itself declared.",
                                f"Declare '{parent}' as well — a census that describes a child "
                                "without its parent cannot say whether the parent appears (§5.9).")
                        elif next((p for p in fields if p.get("name") == parent
                                   and p.get("presence") in _NEGATIVE), None):
                            bad(f"field '{name}' is declared under '{parent}', which is "
                                "'never'/'forbidden'.",
                                f"Remove the child, or change '{parent}'. Declaring members of a "
                                "field that must not appear contradicts the negative claim (§5.9).")
    return out
