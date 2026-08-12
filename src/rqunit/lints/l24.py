"""L24 — a bound literal that duplicates a registered `values` entry (§5.9).

A bound may be a literal or a `{value:…}` reference. Both are legal, and the
literal is right for a one-off. But a literal equal to a fact the store has
already registered is a second copy of that fact, and the copy is the one
nobody updates when the value is gated at Gate 1.

`finding`, not `error`: two numbers can coincide innocently — a max length of 8
and an unrelated retry count of 8 are not the same fact — so the tool reports
the coincidence and lets a human judge. Erroring on a guess would teach people
to bypass the gate.

**With more than one candidate the suggestion asks rather than answers.** The
rule cannot know which registered fact a bare literal meant, and it used to
offer the alphabetically first match as though it did — so a census declaring a
64-character token was told to reference an Argon2 memory parameter that also
happened to equal 64, with the right answer sitting in the same sentence. In a
framework built for agent participation the suggestion is the half that gets
applied, so a suggestion phrased as an instruction has to be one the rule can
stand behind. One candidate is an instruction; several is a question.
"""

from ..violations import Violation
from .base import lint, rel

_BOUND_KEYS = ("max_chars", "min_chars", "min", "max", "min_items", "max_items")


def _registered(manifest):
    """Flatten `values` into dotted key -> scalar."""
    out = {}

    def walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{path}.{k}" if path else k)
        elif node is not None:
            out[path] = node
    walk(manifest.raw.get("values") or {}, "")
    return out


@lint("L24")
def run(store):
    out = []
    manifests = store.manifests()
    shared = manifests.get("shared")
    shared_values = _registered(shared) if shared else {}
    for service, manifest in manifests.items():
        if service == "shared":
            continue
        known = {**shared_values, **_registered(manifest)}
        if not known:
            continue
        for e in manifest.raw.get("endpoints") or []:
            for direction in ("inbound", "outbound"):
                slot = e.get(direction)
                if not isinstance(slot, dict):
                    continue
                fields = slot.get("fields")
                for f in fields if isinstance(fields, list) else []:
                    for key in _BOUND_KEYS:
                        literal = f.get(key)
                        if not isinstance(literal, int):
                            continue
                        matches = sorted(k for k, v in known.items() if v == literal)
                        if not matches:
                            continue
                        if len(matches) == 1:
                            suggestion = (
                                f"Reference it instead: {key}: \"{{value:{matches[0]}}}\". "
                                "A bound written twice is a bound that can diverge — and "
                                "the copy is what a gated change misses (§5.9). If the "
                                "numbers coincide by accident, leave it.")
                        else:
                            suggestion = (
                                f"{len(matches)} registered values equal {literal} — reference "
                                f"the one this bound MEANS ({key}: \"{{value:<the fact>}}\"), or "
                                "leave the literal if the match is coincidental. This rule "
                                "compares numbers and cannot tell which fact you meant, so it "
                                "does not choose for you: a bound referencing the wrong fact is "
                                "worse than a duplicated one (§5.9).")
                        out.append(Violation(
                            rule="L24", severity="finding",
                            artifact=f"{service}:endpoints.{e['id']}.{direction}.{f.get('name')}",
                            path=rel(store, manifest.path),
                            message=(f"`{key}: {literal}` restates a registered value "
                                     f"({', '.join(matches)})."),
                            suggestion=suggestion,
                        ))
    return out
