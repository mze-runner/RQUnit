"""The off-ramp (spec §6.6): removing the trace annotations adoption asked for.

Adoption is not a one-way door. A consumer writes `verifies` traces into their
own test sources because the framework asked them to, so the framework owes
them a way to take those marks back — after off-boarding, or before re-adopting
onto a corpus whose ids no longer mean what the marks say. Without it the only
remedies are a hand-rolled `sed` and a marker invented per consumer, which is
how a workaround becomes a convention nobody validates.

The split is the same one that governs every adapter role. CORE decides WHICH
tokens go: it alone knows which RUs are active, so a stripper is never asked to
judge whether a trace is stale. The ADAPTER rewrites the sources, because only
it knows what an annotation looks like in its idiom — core has carried no
language knowledge since the scanner left it. Core writes the returned files,
exactly as it does for an emitter, which keeps the path-escape rejection and
the dry run in one place.

Orphans by default: only tokens naming no active RU are removed, so a strip run
mid-migration cannot destroy links already re-pointed. `--all` is off-boarding,
and takes the `infrastructure` markers with it — those are the framework's
vocabulary too.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .config import load as load_config
from .errors import BadConfig
from .invoke import run_role
from .store import Store
from .trace import SCANNED_SCHEMA, _to_checks

RESPONSE_SCHEMA = "stripped-files.schema.json"


@dataclass
class StripPlan:
    """What core decided, before any adapter ran."""

    per_stack: dict[str, list[dict]] = field(default_factory=dict)
    # Declared, scanned stacks that cannot be stripped. Reported, never
    # silently skipped: a stack adoptable but not un-adoptable is a capability
    # statement the operator has to see before they believe a clean sweep.
    unavailable: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(len(entries) for entries in self.per_stack.values())


@dataclass
class StripResult:
    written: list[str] = field(default_factory=list)     # repo-relative paths
    stripped: list[str] = field(default_factory=list)    # check ids


def plan(store: Store, root: Path, everything: bool = False) -> StripPlan:
    """Which tokens to remove, per stack — the judgment, made once, in core."""
    active = {ru.id for ru in store.rus() if ru.status == "active"}
    out = StripPlan()

    for stack in load_config(root).stacks:
        if stack.adapter.scanner is None:
            continue                       # unobserved; `trace` already says so
        if stack.adapter.stripper is None:
            out.unavailable.append(stack.name)
            continue
        entries = []
        for check in _to_checks(run_role(root, stack, "scanner",
                                         schema=SCANNED_SCHEMA)):
            remove = [token for token in check.verifies
                      if everything
                      or (token != "infrastructure" and token not in active)]
            if remove:
                entries.append({"id": check.id, "path": check.path,
                                "fn": check.fn, "remove": remove})
        out.per_stack[stack.name] = entries
    return out


def apply(root: Path, decided: StripPlan, write: bool) -> StripResult:
    """Hand each stack its own instruction, validate the answer, write.

    The response must be a SUBSET of the request: a stripper that reports
    touching a check nobody asked about has exceeded its instruction, and an
    off-ramp that silently edits more than it was told to is worse than none.
    """
    stacks = {stack.name: stack for stack in load_config(root).stacks}
    result = StripResult()

    for name, entries in decided.per_stack.items():
        if not entries:
            continue
        where = f"[stacks.{name}.adapter] stripper"
        # Artifact mode is legitimate for an observation — a pipeline step
        # already looked and wrote down what it saw. A stripper answers a
        # request core computes moments earlier, so a file cannot be that
        # answer: it would be some earlier run's edits applied to today's
        # source. Declared cmd only, and said out loud rather than silently
        # writing the stale thing.
        if stacks[name].adapter.stripper.artifact:
            raise BadConfig(where,
                            "artifact mode cannot serve a stripper — its answer depends "
                            "on a request computed from today's store, so a committed "
                            "file would be an earlier run's edits applied to current "
                            "source. Declare cmd = [...] and let core run it")
        payload = json.dumps({"contract_version": 1, "checks": entries},
                             indent=2) + "\n"
        response = run_role(root, stacks[name], "stripper",
                            schema=RESPONSE_SCHEMA, stdin_payload=payload)

        overreach = sorted(set(response["stripped"]) - {e["id"] for e in entries})
        if overreach:
            raise BadConfig(where,
                            f"reported stripping {len(overreach)} check(s) it was not "
                            f"asked about ({', '.join(overreach[:3])}) — the request is "
                            "the complete instruction, and a stripper that edits beyond "
                            "it cannot be trusted with source")

        for entry in response["files"]:
            relative = entry["path"]
            if Path(relative).is_absolute() or ".." in Path(relative).parts:
                raise BadConfig(where,
                                f"returned path '{relative}' escaping the consumer root "
                                "— a stripper rewrites the files it was handed, nothing "
                                "else")
            if write:
                (Path(root) / relative).write_text(entry["content"])
            result.written.append(relative)
        result.stripped.extend(response["stripped"])

    result.written = sorted(set(result.written))
    result.stripped = sorted(set(result.stripped))
    return result
