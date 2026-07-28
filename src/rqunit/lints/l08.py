"""L8 — forbidden fields absent (spec §3.2). The RU schema's
additionalProperties:false is the structural backstop; this lint reads the
raw files directly so it still reports (with the L8-specific message) when
the store cannot fully load."""

from pathlib import Path

import yaml

from ..violations import Violation
from .base import lint, rel

FORBIDDEN = ("priority", "estimate", "assignee", "role", "permission", "sprint", "iteration")


@lint("L8")
def run(store):
    out = []
    ru_dir = Path(store.root) / "spec" / "ru"
    if not ru_dir.is_dir():
        return out
    for path in sorted(ru_dir.glob("RU-*.yaml")):
        try:
            data = yaml.safe_load(path.read_text())
        except yaml.YAMLError:
            continue  # schema stage reports malformed files
        if not isinstance(data, dict):
            continue
        for field in FORBIDDEN:
            if field in data:
                out.append(Violation(
                    rule="L8", severity="error", artifact=data.get("id", path.stem),
                    path=rel(store, path),
                    message=f"forbidden field '{field}' — workflow metadata never lives on an RU (§3.2).",
                    suggestion="Priority/estimation/assignment belong to TASK nodes in the task system, not the store."))
    return out
