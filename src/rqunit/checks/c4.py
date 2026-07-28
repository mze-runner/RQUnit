"""C4 — method+path uniqueness per service, upgrade paths included; templates
normalize before comparison (spec §10.2, donor note)."""

import re
from collections import defaultdict

from ..lints.base import rel
from ..violations import Violation
from .base import check

_TEMPLATE = re.compile(r"\{[^}]+\}")


def _norm(path: str) -> str:
    return _TEMPLATE.sub("{}", path)


@check("C4")
def run(store):
    out = []
    for service, manifest in store.manifests().items():
        seen = defaultdict(list)
        for e in manifest.raw.get("endpoints") or []:
            seen[(e["method"], _norm(e["path"]))].append(f"endpoint:{e['id']}")
        upgrade_paths = {}
        for c in manifest.raw.get("channels") or []:
            key = _norm(c["upgrade_path"])
            upgrade_paths[key] = c["id"]
            for (method, path), ids in list(seen.items()):
                if path == key:
                    seen[(method, path)].append(f"channel:{c['id']}")
        dup_channels = defaultdict(list)
        for c in manifest.raw.get("channels") or []:
            dup_channels[_norm(c["upgrade_path"])].append(c["id"])
        for (method, path), ids in seen.items():
            if len(ids) > 1:
                out.append(_v(store, manifest, service,
                              f"{method} {path} declared by {', '.join(ids)} (template-normalized)."))
        for path, ids in dup_channels.items():
            if len(ids) > 1:
                out.append(_v(store, manifest, service,
                              f"upgrade path {path} declared by channels {', '.join(ids)}."))
    return out


def _v(store, manifest, service, message):
    return Violation(rule="C4", severity="error", artifact=service, path=rel(store, manifest.path),
                     message=message,
                     suggestion="Method+path (upgrade paths included) must be unique per service (§10.2 C4).")
