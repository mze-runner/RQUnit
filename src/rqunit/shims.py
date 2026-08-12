"""Statechart shim registrations (spec §6.3).

A generated model suite asserts against a `StatechartSubject` the application
provides. Until that shim exists the suite is ignored-with-reason: it cannot
execute, so it proves nothing. This module reads the store's claims about
which models have one — consumer data at
`spec/framework/shims.yaml`, beside the coverage policy and the conformance
exceptions, because it is a human claim, not an observation.

The registration is load-bearing precisely because it is a claim: L21 counts
an unregistered model's verification as zero mechanical depth, and the report
shows its suite as pending-shim. That is what stops declared depth from
exceeding provable depth.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .errors import BadConfig

SHIMS_PATH = ("spec", "framework", "shims.yaml")


def load_shims(root: Path) -> list[dict]:
    """Registered shims, or [] when the store carries no file (a store that
    has registered nothing and a store predating the file mean the same
    thing: no model's suite is claimed to execute)."""
    path = Path(root).joinpath(*SHIMS_PATH)
    if not path.is_file():
        return []
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as e:
        raise BadConfig(str(path), f"not parseable YAML: {e}") from e
    entries = data.get("shims") or []
    if not isinstance(entries, list):
        raise BadConfig(str(path), "`shims` must be a list of registration entries")
    # Malformed entries are RETURNED, not filtered: dropping a bare
    # `- MDL-order-lifecycle` would leave the model reading as unregistered,
    # and the consumer chasing an L21 warning telling them to register a shim
    # they believe they just registered. C15 reports the shape instead.
    return list(entries)


def registered_models(root: Path) -> set[str]:
    """Bare model ids whose shim is registered (MDL- prefix stripped, as
    everywhere else the store names a model). A malformed entry registers
    nothing — C15 is what tells the consumer why."""
    return {str(e.get("model", "")).removeprefix("MDL-")
            for e in load_shims(root)
            if isinstance(e, dict) and e.get("model")}
