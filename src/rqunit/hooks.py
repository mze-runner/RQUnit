"""H1/H2 hook logic (TASK-060/061, spec §10.3) — pure functions, tested by
harness; the agent-runtime wiring is a thin shell layer.

H1 (pre-write, blocking): a write matching any in-context `must_not_touch`
glob is blocked, citing the RU that imposes the boundary. H1 blocks NEGATIVE
scope only — a path outside `owns` is H2's business, not H1's.

H2 (post-write, never blocking): writes outside the union of in-context
`owns` globs are appended to spec/projections/scope-audit.jsonl (accepted
residual risk, audited).

Boundary source (plan D-P5.1/2): the active packet named by
spec/packets/.active (or $SPEC_ACTIVE_PACKET), whose `# 5. Boundaries`
section carries a fenced yaml block:

    task: TASK-0007
    owns: [service-auth/domain, service-auth/application]
    must_not_touch:
      - { glob: service-core, ru: RU-0142 }
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

_BOUNDARIES = re.compile(
    r"^#+\s*5\.\s*Boundaries.*?```yaml\n(?P<block>.*?)```", re.DOTALL | re.MULTILINE
)


@dataclass(frozen=True)
class Boundaries:
    task: str
    owns: list[str] = field(default_factory=list)
    must_not_touch: list[dict] = field(default_factory=list)  # {glob, ru}


def active_packet_path(root: Path) -> Path | None:
    override = os.environ.get("SPEC_ACTIVE_PACKET")
    if override:
        p = Path(override)
        return p if p.is_file() else None
    marker = Path(root) / "spec" / "packets" / ".active"
    if not marker.is_file():
        return None
    packet = Path(root) / "spec" / "packets" / marker.read_text().strip()
    return packet if packet.is_file() else None


def load_boundaries(packet: Path) -> Boundaries | None:
    m = _BOUNDARIES.search(packet.read_text())
    if not m:
        return None
    data = yaml.safe_load(m.group("block")) or {}
    return Boundaries(
        task=str(data.get("task", packet.stem)),
        owns=[str(g) for g in data.get("owns") or []],
        must_not_touch=[
            e if isinstance(e, dict) else {"glob": str(e), "ru": "unknown"}
            for e in data.get("must_not_touch") or []
        ],
    )


def path_matches(path: str, glob: str) -> bool:
    """D-P5.3: bare globs are containment prefixes; wildcards use fnmatch."""
    path, glob = path.strip("/"), glob.strip("/")
    if any(c in glob for c in "*?["):
        return fnmatch.fnmatch(path, glob) or fnmatch.fnmatch(path, glob + "/*")
    return path == glob or path.startswith(glob + "/")


def relativize(root: Path, path: str) -> str:
    p = Path(path)
    if not p.is_absolute():
        # Relative paths are taken as repo-root-relative AS-IS — resolving
        # against the CLI's own cwd would mangle them.
        return str(p)
    try:
        return str(p.resolve().relative_to(Path(root).resolve()))
    except ValueError:
        return str(p)


def h1_verdict(root: Path, path: str) -> tuple[bool, str | None]:
    """(blocked, message). Blocks only on a must_not_touch match."""
    packet = active_packet_path(root)
    if packet is None:
        return False, None
    boundaries = load_boundaries(packet)
    if boundaries is None:
        return False, None
    rel = relativize(root, path)
    for entry in boundaries.must_not_touch:
        if path_matches(rel, entry["glob"]):
            return True, (
                f"H1: write to '{rel}' is inside must_not_touch glob '{entry['glob']}' "
                f"imposed by {entry.get('ru', 'unknown')} (task {boundaries.task}). "
                "Out-of-boundary work needs its own task and packet — or the RU's scope is "
                "wrong, which is a GAP, not a workaround."
            )
    return False, None


def h2_record(root: Path, path: str) -> dict | None:
    """Audit entry for an out-of-owns write, or None when in bounds/inert.
    Appending is the caller's job; H2 never blocks."""
    packet = active_packet_path(root)
    if packet is None:
        return None
    boundaries = load_boundaries(packet)
    if boundaries is None or not boundaries.owns:
        return None
    rel = relativize(root, path)
    if any(path_matches(rel, glob) for glob in boundaries.owns):
        return None
    return {
        "task": boundaries.task,
        "path": rel,
        "owns": boundaries.owns,
        "matched": False,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def append_audit(root: Path, record: dict) -> None:
    log = Path(root) / "spec" / "projections" / "scope-audit.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "a") as f:
        f.write(json.dumps(record) + "\n")
