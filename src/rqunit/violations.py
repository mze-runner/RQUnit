"""Violation model and report format (formats §4). One JSON shape for every
CLI; human-readable text is derived from the JSON, never a separate code path.
"""

from __future__ import annotations

import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .schemas import installed_version

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
        "tool_version": installed_version(),
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


def empty_store_findings(store) -> list["Violation"]:
    """"This store holds no requirements" — said out loud, in both reports.

    An empty store used to produce output byte-identical in spirit to a mature,
    healthy one: zero errors, zero warnings, empty violation list. The framework's
    stated position is that visible debt is by design and status belongs in tool
    output, and an empty store is the largest debt there is — so the two commands
    a consumer runs most often said nothing about the only thing that was true.

    `finding`, so it never touches an exit code: nothing is WRONG with a store on
    its first day. It is keyed on "no RUs at all", never on a count — a rule that
    fired below some threshold would be a state-pinned assertion wearing a lint,
    and ordinary growth would have to keep re-tuning it. It disappears the moment
    the first requirement lands.

    Not a numbered rule, for the reason `SCHEMA` and `CONFIG` are not: those
    number-free labels exist for facts about the store as a whole rather than
    about an artifact a rule can point at, and a numbered rule here would have to
    be issued twice — once in the lint family and once in the check family — to
    reach both reports. One fact, one label, both commands."""
    if store.rus():
        return []
    return [Violation(
        rule="STORE", severity="finding", artifact="store", path="spec/ru",
        message="this store holds no requirements — nothing was checked.",
        suggestion="Capture intent under spec/intent/, register the tags and actors your "
                   "requirements will use, then compile drafts with one acceptance "
                   "criterion each (§8.1). Until then every gate here is green because "
                   "there is nothing to judge, which is not the same as healthy.")]


def schema_violation(error, root) -> "Violation":
    """The one rendering of "this store will not load".

    Every verb that loads a store hits this, and it used to be spelled once per
    CLI — which is how the two copies came to differ in path handling and in
    whether they carried a suggestion at all. A store that cannot load is a
    finding, not a tool error, and it is the FIRST thing a new consumer meets,
    so it gets the same teaching treatment as every other violation."""
    from pathlib import Path
    where = str(root)
    if error.path:
        try:
            where = str(Path(error.path).relative_to(Path(root).resolve()))
        except ValueError:
            where = error.path
    # StoreError prefixes its own path; the report already carries one, and an
    # absolute path printed twice reads as two different files.
    message = str(error).removeprefix(f"{error.path}: ") if error.path else str(error)
    return Violation(
        rule="SCHEMA", severity="error",
        artifact=Path(error.path).name if error.path else "store",
        path=where, message=message,
        suggestion="Fix the artifact named above; the message locates the key. "
                   "Shapes are pinned in formats.md — §1 for ids and filenames, "
                   "§5.4 for manifests, §7 for RUs — and nothing else has run: "
                   "a store that does not validate cannot be loaded to be judged.",
    )
