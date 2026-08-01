"""C12 — path placeholders and `in: path` fields reconcile (spec §5.9).

The route template must keep its placeholders: method+path is the surface's
identity for C4 uniqueness and for extractor matching, and `/orders/{id}`
stripped of its placeholder collapses into `/orders`. So a path parameter is
named twice — once in the template, once in the census that constrains it. This
check makes that a reconciliation rather than a duplication.
"""

import re

from ..lints.base import rel
from ..violations import Violation
from .base import check

_PLACEHOLDER = re.compile(r"\{([^{}]*)\}")


@check("C12")
def run(store):
    out = []
    for service, manifest in store.manifests().items():
        for e in manifest.raw.get("endpoints") or []:
            where = f"{service}:endpoints.{e['id']}"
            path_str = e.get("path") or ""
            placeholders = _PLACEHOLDER.findall(path_str)
            inbound = e.get("inbound")
            fields = inbound.get("fields") if isinstance(inbound, dict) else None
            declared = [f.get("name") for f in fields or [] if f.get("in") == "path"]

            def bad(message, suggestion):
                out.append(Violation(rule="C12", severity="error", artifact=where,
                                     path=rel(store, manifest.path),
                                     message=message, suggestion=suggestion))

            for name in {p for p in placeholders if placeholders.count(p) > 1}:
                bad(f"path '{path_str}' uses the placeholder '{{{name}}}' more than once.",
                    "Give each placeholder a distinct name (e.g. '{order_id}' and '{item_id}'). "
                    "Repeated names cannot be constrained separately, and a token cannot say "
                    "which one it means (§5.9).")
            for name in placeholders:
                if name and name not in declared:
                    bad(f"path placeholder '{{{name}}}' has no `in: path` field.",
                        f"Declare it in `inbound.fields` as "
                        f"{{ name: {name}, in: path, presence: required, … }} — a path segment is "
                        "client-supplied input like any other (§5.9).")
            for name in declared:
                if name not in placeholders:
                    bad(f"field '{name}' declares `in: path`, but '{path_str}' has no such "
                        "placeholder.",
                        "Fix the field name or the route template — they name the same segment, "
                        "so one of the two is stale (§5.9).")
    return out
