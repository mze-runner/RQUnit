"""The check-evidence ledger (spec §6.8).

A test written by an agent that has already read the implementation, asserting
that implementation's shape, is green and worthless — it discriminates
nothing. Nothing in the framework could tell such a check from one that earns
its green, because both look identical at rest. What separates them is
history: a check that has *ever* been observed failing has demonstrated it can
fail, and one that has only ever been green has demonstrated nothing.

So the framework keeps a ledger of firsts. A per-stack evidence probe reports
what a run observed (contract: interfaces/check-evidence.schema.json); this
module folds those outcomes in, recording only the FIRST pass and the FIRST
failure per check. First-observation-wins: the ledger is a record of what has
been demonstrated, so a second red adds nothing a first red did not already
prove, and re-recording it would make an append-only file grow with every CI
run while saying the same thing.

Not to be confused with AUDIT records, which are the consumer system's
evidence to its own operators (§5.10). This ledger is the framework's evidence
about its own checks.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .errors import BadConfig

LEDGER_PATH = ("spec", "check-evidence", "check-evidence.jsonl")

FIRST_GREEN = "first_green"
FIRST_RED = "first_red"

_OUTCOME_TO_FIRST = {"passed": FIRST_GREEN, "failed": FIRST_RED}


@dataclass(frozen=True)
class Observation:
    check_id: str
    observation: str        # first_green | first_red
    at: str
    source: str


def ledger_path(root: Path) -> Path:
    return Path(root).joinpath(*LEDGER_PATH)


def load_ledger(root: Path) -> list[Observation]:
    """Every recorded first, oldest first. An absent ledger is not an error:
    a store that has never recorded evidence has observed nothing, which is a
    different claim from having observed a green."""
    path = ledger_path(root)
    if not path.is_file():
        return []
    out = []
    for number, line in enumerate(path.read_text().splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as e:
            raise BadConfig(f"{path}:{number}", f"not parseable JSON: {e}") from e
        if not isinstance(entry, dict) or entry.get("observation") not in (
                FIRST_GREEN, FIRST_RED) or not entry.get("check_id"):
            raise BadConfig(f"{path}:{number}",
                            "each line is one recorded first: "
                            "{check_id, observation: first_green|first_red, at, source}")
        out.append(Observation(check_id=str(entry["check_id"]),
                               observation=str(entry["observation"]),
                               at=str(entry.get("at", "")),
                               source=str(entry.get("source", ""))))
    return out


def recorded(root: Path) -> dict[str, set[str]]:
    """check id → the firsts already demonstrated for it."""
    out: dict[str, set[str]] = {}
    for entry in load_ledger(root):
        out.setdefault(entry.check_id, set()).add(entry.observation)
    return out


def never_red(root: Path) -> set[str]:
    """Checks demonstrated green and never demonstrated failing — the class
    L26 reports. A check with no evidence at all is NOT in this set: absence
    of evidence is not evidence of absence, and a store that has never
    recorded a run would otherwise light up entirely."""
    return {check for check, firsts in recorded(root).items()
            if FIRST_GREEN in firsts and FIRST_RED not in firsts}


def fold(root: Path, artifact: dict, at: str, source: str) -> list[Observation]:
    """The firsts this run demonstrates that the ledger does not already
    carry. Pure: it computes, the caller appends. `artifact` must already
    have passed check-evidence.schema.json — every caller validates, and this
    reads the shape the contract guarantees."""
    already = recorded(root)
    fresh: list[Observation] = []
    seen: set[tuple[str, str]] = set()
    for observation in artifact["observations"]:
        check_id = observation["check_id"]
        first = _OUTCOME_TO_FIRST[observation["outcome"]]
        if first in already.get(check_id, set()) or (check_id, first) in seen:
            continue
        seen.add((check_id, first))
        fresh.append(Observation(check_id=check_id, observation=first,
                                 at=at, source=source))
    return sorted(fresh, key=lambda o: (o.check_id, o.observation))


def append(root: Path, entries: list[Observation]) -> None:
    """Append-only, one JSON object per line — the same discipline as Gate 2
    records: history is added to, never rewritten."""
    if not entries:
        return
    path = ledger_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as handle:
        for entry in entries:
            handle.write(json.dumps({"check_id": entry.check_id,
                                     "observation": entry.observation,
                                     "at": entry.at,
                                     "source": entry.source},
                                    sort_keys=True) + "\n")
