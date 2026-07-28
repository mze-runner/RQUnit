"""Violation model and report format (formats §4). One JSON shape for every
CLI; human-readable text is derived from the JSON, never a separate code path.
"""

from __future__ import annotations

import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

TOOL_VERSION = "0.1.0"

SEVERITIES = ("error", "warning", "finding")


@dataclass(frozen=True)
class Violation:
    rule: str                      # "L2", "C4", ...
    severity: str                  # error | warning | finding
    artifact: str                  # "RU-0142", "service-orders", ...
    path: str                      # repo-relative where possible
    message: str
    line: int | None = None
    suggestion: str | None = None

    def __post_init__(self):
        assert self.severity in SEVERITIES, self.severity


def _store_commit(root: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        sha = out.stdout.strip()
        if out.returncode == 0 and sha:
            dirty = subprocess.run(
                ["git", "-C", str(root), "status", "--porcelain"],
                capture_output=True, text=True, timeout=5,
            ).stdout.strip()
            return "WORKTREE" if dirty else sha
    except (OSError, subprocess.TimeoutExpired):
        pass
    return "WORKTREE"


def build_report(tool: str, violations: list[Violation], checked_files: int, root: Path) -> dict:
    return {
        "tool": tool,
        "tool_version": TOOL_VERSION,
        "store_commit": _store_commit(root),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "summary": {
            "errors": sum(v.severity == "error" for v in violations),
            "warnings": sum(v.severity == "warning" for v in violations),
            "checked_files": checked_files,
        },
        "violations": [
            {k: v for k, v in asdict(x).items() if v is not None} for x in violations
        ],
    }


def render_text(report: dict) -> str:
    """`--format text` rendering, derived from the JSON document."""
    lines = [
        f"{report['tool']} {report['tool_version']} · store {report['store_commit']} · "
        f"{report['summary']['checked_files']} files · "
        f"{report['summary']['errors']} error(s), {report['summary']['warnings']} warning(s)"
    ]
    for v in report["violations"]:
        loc = f"{v['path']}:{v['line']}" if v.get("line") else v["path"]
        lines.append(f"[{v['rule']}/{v['severity']}] {v['artifact']} ({loc}): {v['message']}")
        if v.get("suggestion"):
            lines.append(f"    suggestion: {v['suggestion']}")
    return "\n".join(lines)


def exit_code(report: dict, strict: bool = False) -> int:
    """0 = no errors (warnings allowed unless --strict), 1 = errors present."""
    if report["summary"]["errors"]:
        return 1
    if strict and report["summary"]["warnings"]:
        return 1
    return 0
