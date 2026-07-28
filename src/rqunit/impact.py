"""Manifest impact reporter (TASK-051, spec §5.5). A manifest edit is either
additive (new entry — changes no frozen RU's meaning) or mutating (changed or
deleted fact — silently changes every frozen RU referencing it). Mutating
edits require an impact report at Gate 1: every RU and committed packet
referencing the changed key."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .lints.base import manifest_value_leaves
from .parser.tokens import extract
from .store import Store


@dataclass(frozen=True)
class Change:
    kind: str        # additive | mutating
    section: str     # values | endpoints | messages | channels | problem_types | audit_events | vocabularies
    key: str
    detail: str


@dataclass
class ImpactReport:
    service: str
    changes: list[Change] = field(default_factory=list)
    affected_rus: dict[str, list[str]] = field(default_factory=dict)   # key -> [RU ids]
    affected_packets: dict[str, list[str]] = field(default_factory=dict)

    @property
    def mutating(self) -> list[Change]:
        return [c for c in self.changes if c.kind == "mutating"]


def _facts(raw: dict) -> dict[tuple[str, str], object]:
    out: dict[tuple[str, str], object] = {}
    for dotted, value in manifest_value_leaves(raw.get("values") or {}).items():
        out[("values", dotted)] = value
    for key, value in (raw.get("problem_types") or {}).items():
        out[("problem_types", key)] = value
    for key, value in (raw.get("vocabularies") or {}).items():
        out[("vocabularies", key)] = value
    for e in raw.get("audit_events") or []:
        out[("audit_events", e["code"])] = e
    for section in ("endpoints", "messages", "channels"):
        for e in raw.get(section) or []:
            out[(section, e["id"])] = e
    return out


def diff_manifests(old_raw: dict, new_raw: dict) -> list[Change]:
    old_facts, new_facts = _facts(old_raw), _facts(new_raw)
    changes = []
    for (section, key), value in new_facts.items():
        if (section, key) not in old_facts:
            changes.append(Change("additive", section, key, "new fact"))
        elif old_facts[(section, key)] != value:
            changes.append(Change("mutating", section, key, "fact changed"))
    for (section, key) in old_facts:
        if (section, key) not in new_facts:
            changes.append(Change("mutating", section, key, "fact deleted"))
    return changes


_SECTION_TO_KIND = {"values": "value", "problem_types": "problem", "audit_events": "audit",
                    "vocabularies": "vocab", "endpoints": "endpoint", "messages": "message",
                    "channels": "channel"}


def build_report(store: Store, service: str, changes: list[Change]) -> ImpactReport:
    report = ImpactReport(service=service, changes=changes)
    mutated = {(c.section, c.key) for c in changes if c.kind == "mutating"}
    if not mutated:
        return report
    for ru in store.rus():
        scope = store.scope_service(ru)
        tokens, _ = extract(ru.raw["statement"])
        for t in tokens:
            target_service = t.qualifier or scope or "shared"
            if target_service != service and not (t.qualifier is None and service == "shared"):
                continue
            for section, key in mutated:
                if _SECTION_TO_KIND[section] == t.kind and (key == t.key or key.startswith(t.key + ".")):
                    report.affected_rus.setdefault(f"{section}.{key}", []).append(ru.id)
    packets = Path(store.root) / "spec" / "packets"
    if packets.is_dir():
        for packet in sorted(packets.glob("*.packet.md")):
            text = packet.read_text()
            for section, key in mutated:
                if key in text:
                    report.affected_packets.setdefault(f"{section}.{key}", []).append(packet.name)
    return report


def manifest_at_ref(root: Path, ref: str, service: str) -> dict | None:
    rel = f"spec/manifests/{service}.manifest.yaml"
    proc = subprocess.run(["git", "-C", str(root), "show", f"{ref}:{rel}"],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        return None
    return yaml.safe_load(proc.stdout)


def render(report: ImpactReport) -> str:
    lines = [f"impact report — {report.service}"]
    if not report.changes:
        lines.append("  no manifest changes")
    for c in report.changes:
        lines.append(f"  [{c.kind}] {c.section}.{c.key} ({c.detail})")
        if c.kind == "mutating":
            for ru_id in report.affected_rus.get(f"{c.section}.{c.key}", []):
                lines.append(f"      affects {ru_id}")
            for packet in report.affected_packets.get(f"{c.section}.{c.key}", []):
                lines.append(f"      affects packet {packet}")
    return "\n".join(lines)
