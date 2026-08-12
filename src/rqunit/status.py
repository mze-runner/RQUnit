"""Computed status engine (spec §10.4). No manual status field exists — these
are derived, and v1 is deliberately conservative (plan D-P4.1): a verification
entry counts as PASSING only when that is provable today — a human entry with
a passing Gate 2 record dated after the gate stamp. Mechanical pass-states
(test/model results) arrive with Phases 6–7; until then `done` stays
false rather than lying.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from .canonical import canonical_hash, expected_fingerprints
from .store import Ru, Store


@dataclass(frozen=True)
class RuStatus:
    done: bool
    blocked: bool
    failing: bool
    debt: bool
    reviewed: bool
    suspect: bool


def gate2_records(store: Store, ru_id: str) -> list[dict]:
    """Append-only Gate 2 verdicts under spec/reviews/<RU id>/ (formats §9)."""
    out = []
    directory = Path(store.root) / "spec" / "reviews" / ru_id
    if directory.is_dir():
        for path in sorted(directory.glob("*.yaml")):
            record = yaml.safe_load(path.read_text())
            if isinstance(record, dict):
                out.append(record)
    return out


def _stamp_valid(ru: Ru) -> bool:
    stamp = ru.raw.get("gate1_stamp")
    return bool(stamp) and stamp.get("hash") == canonical_hash(ru.raw)


def _human_passed(ru: Ru, store: Store) -> bool:
    stamp = ru.raw.get("gate1_stamp") or {}
    stamped_at = stamp.get("at", "")
    records = gate2_records(store, ru.id)
    for entry in ru.raw.get("verification") or []:
        if entry.get("type") != "human":
            continue
        ok = any(
            r.get("verdict") == "pass" and r.get("criterion") == entry.get("criterion")
            and r.get("at", "") > stamped_at
            for r in records
        )
        if not ok:
            return False
    return True


def compute(store: Store, ru: Ru) -> RuStatus:
    entries = ru.raw.get("verification") or []
    blocked = any("TODO(" in str(e.get("ref", "")) for e in entries)
    stamp_present = "gate1_stamp" in ru.raw
    failing = (stamp_present and not _stamp_valid(ru)) or _any_stale_model(store, entries)
    debt = bool(entries) and all(e.get("type") == "human" for e in entries)
    suspect = _any_fingerprint_mismatch(store, ru)
    human_ok = _human_passed(ru, store)
    mechanical = [e for e in entries if e.get("type") != "human"]
    # v1: mechanical passes are not yet provable — done only for human-only RUs
    # whose every criterion has a passing, post-stamp Gate 2 record.
    done = (not blocked and not failing and not mechanical
            and bool(entries) and human_ok and stamp_present and _stamp_valid(ru))
    reviewed = stamp_present and _stamp_valid(ru) and human_ok
    return RuStatus(done=done, blocked=blocked, failing=failing,
                    debt=debt, reviewed=reviewed, suspect=suspect)


def _any_stale_model(store: Store, entries: list) -> bool:
    models = store.models()
    for e in entries:
        if e.get("type") == "model":
            model = models.get(str(e.get("ref", "")).removeprefix("MDL-"))
            if model and e.get("model_hash") != model.content_hash:
                return True
    return False


def _any_fingerprint_mismatch(store: Store, ru: Ru) -> bool:
    recorded = ru.raw.get("link_fingerprints") or {}
    if not recorded:
        return False
    current = expected_fingerprints(store, ru.raw)
    return any(current.get(target) != fp for target, fp in recorded.items())
