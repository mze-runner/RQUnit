"""spec-trace (spec §6.6): bidirectional traceability, computed.

Forward: every non-infrastructure check carries a resolvable `verifies` trace
(annotated in the stack's own idiom, or inherited via trace-map.json for
generated suites). Backward: every RU test ref resolves to a real check. Both
directions plus orphan manifest facts (C7) land in one report pair:
spec/projections/orphans.{md,json}.

Test discovery is an adapter observation: each declared stack's scanner role
reports the checks its tree carries (contract:
interfaces/scanned-checks.schema.json), and this module owns every judgment —
what resolves, what blocks, and what "new" means. L14 newness is base-vs-head
set difference over the scanner's own observations, never diff inspection:
a regex for "an added test line" is language knowledge, and language
knowledge does not live in core.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from . import ids
from .checks.base import run_checks
from .config import Stack, load as load_config
from .invoke import run_role, validate_payload
from .status import compute
from .store import Store

SCANNED_SCHEMA = "scanned-checks.schema.json"


@dataclass(frozen=True)
class TestCheck:
    id: str                 # stack-qualified (Rust: package::file_stem::fn)
    path: str               # repo-relative file
    fn: str
    verifies: tuple[str, ...]   # RU ids, or ("infrastructure",), or ()


def _to_checks(data: dict) -> list[TestCheck]:
    return [TestCheck(id=c["id"], path=c["path"], fn=c["fn"],
                      verifies=tuple(c["verifies"]))
            for c in data["checks"]]


def _scanner_stacks(root: Path) -> list[Stack]:
    return [stack for stack in load_config(root).stacks
            if stack.adapter.scanner is not None]


def unscanned_stacks(root: Path) -> list[str]:
    """Declared stacks whose tests nothing observes. Reported, never silently
    skipped: a stack without a scanner role is a capability statement the
    reader must get to see."""
    return [stack.name for stack in load_config(root).stacks
            if stack.adapter.scanner is None]


def scan_tests(root: Path) -> list[TestCheck]:
    """Every declared scanner's observation, merged. Check ids are
    stack-qualified by contract, so the union never collides."""
    out: list[TestCheck] = []
    for stack in _scanner_stacks(root):
        out.extend(_to_checks(run_role(root, stack, "scanner", schema=SCANNED_SCHEMA)))
    return out


def load_trace_map(root: Path) -> dict[str, list[str]]:
    path = Path(root) / "spec" / "projections" / "trace-map.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text()).get("checks", {})


@dataclass
class TraceReport:
    dangling_refs: list[str] = field(default_factory=list)      # RU refs → no such test
    invalid_annotations: list[str] = field(default_factory=list)  # verifies → no such active RU
    unverified_rus: list[str] = field(default_factory=list)
    untraced_checks: list[str] = field(default_factory=list)     # burn-down
    infrastructure: list[str] = field(default_factory=list)
    orphan_facts: list[str] = field(default_factory=list)
    unscanned_stacks: list[str] = field(default_factory=list)    # capability gaps

    @property
    def blocking(self) -> list[str]:
        return self.dangling_refs + self.invalid_annotations


def build_report(store: Store, root: Path,
                 checks: list[TestCheck] | None = None) -> TraceReport:
    report = TraceReport()
    checks = scan_tests(root) if checks is None else checks
    check_ids = {c.id for c in checks}
    trace_map = load_trace_map(root)
    active = {ru.id for ru in store.rus() if ru.status == "active"}
    report.unscanned_stacks = unscanned_stacks(root)

    for ru in store.rus():
        if ru.status not in ("active", "draft"):
            continue
        for entry in ru.raw.get("verification") or []:
            ref = str(entry.get("ref", ""))
            if entry.get("type") == "test" and "TODO(" not in ref and ref not in check_ids:
                report.dangling_refs.append(f"{ru.id}: test ref '{ref}' resolves to no scanned test")
        status = compute(store, ru)
        if ru.status == "active" and (status.blocked or status.failing):
            reason = "blocked (TODO refs)" if status.blocked else "failing (stale hash/stamp)"
            report.unverified_rus.append(f"{ru.id}: {reason}")

    for check in checks:
        if check.verifies == ("infrastructure",):
            report.infrastructure.append(check.id)
            continue
        if check.verifies:
            for ru_id in check.verifies:
                if not re.match(ids.permanent_pattern("RU"), ru_id):
                    report.invalid_annotations.append(
                        f"{check.id}: verifies '{ru_id}' is not an RU id (formats §5)")
                elif ru_id not in active:
                    report.invalid_annotations.append(
                        f"{check.id}: verifies {ru_id}, which is not an active RU")
            continue
        if check.id in trace_map:
            continue  # generated suite — inherited via the model's RU links
        report.untraced_checks.append(check.id)

    report.orphan_facts = [
        v.message for v in run_checks(store, only="C7")
    ]
    return report


# ------------------------------------------------------------------ L14 gate

def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args],
                          capture_output=True, text=True)


def _resolve_ref(root: Path, against: str) -> None:
    verify = _git(root, "rev-parse", "--verify", f"{against}^{{commit}}")
    if verify.returncode != 0:
        raise RuntimeError(f"git cannot resolve '{against}': {verify.stderr.strip()} — "
                           "on a shallow CI clone, fetch the base ref first")


def _base_ids(root: Path, against: str) -> set[str]:
    """Every check id the scanners observed at `against` — the base of the
    set difference. Artifact-mode stacks need no checkout: the base
    observation is whatever artifact was committed at that ref. Cmd-mode
    stacks scan a detached worktree of the base. The store may sit below the
    repository top level, so both transports resolve store paths through the
    repo prefix — `REF:path` alone resolves from the top level and would
    read the wrong tree."""
    observed: set[str] = set()
    for stack in _scanner_stacks(root):
        role = stack.adapter.scanner
        if role.artifact:
            observed |= _artifact_ids_at(root, against, role.artifact)
        else:
            observed |= _worktree_ids(root, against, stack)
    return observed


def _artifact_ids_at(root: Path, against: str, artifact: str) -> set[str]:
    # `./` makes git resolve the path against the -C directory (the store
    # root), correct whether or not the store is the repo top level.
    shown = _git(root, "show", f"{against}:./{artifact}")
    if shown.returncode != 0:
        listed = _git(root, "ls-tree", "--name-only", against, "--", artifact)
        if listed.returncode != 0:
            raise RuntimeError(f"git cannot read '{against}': {listed.stderr.strip()}")
        if listed.stdout.strip():
            raise RuntimeError(f"git show {against}:./{artifact} failed: "
                               f"{shown.stderr.strip()}")
        return set()   # the ref exists but the artifact did not: base observed nothing
    data = validate_payload(json.loads(shown.stdout), SCANNED_SCHEMA,
                            f"{against}:{artifact}")
    return {c["id"] for c in data["checks"]}


def _worktree_ids(root: Path, against: str, stack: Stack) -> set[str]:
    prefix = _git(root, "rev-parse", "--show-prefix").stdout.strip()
    with tempfile.TemporaryDirectory(prefix="rqunit-l14-") as scratch:
        base = Path(scratch) / "base"
        added = _git(root, "worktree", "add", "--detach", str(base), against)
        if added.returncode != 0:
            raise RuntimeError(
                f"git worktree add failed for '{against}': {added.stderr.strip()} — "
                "on a shallow CI clone, fetch the base ref first")
        try:
            # The checkout is the whole repository; the scanner is pointed at
            # the store's own subtree within it.
            data = run_role(root, stack, "scanner", schema=SCANNED_SCHEMA,
                            target_root=base / prefix if prefix else base)
            return {c["id"] for c in data["checks"]}
        finally:
            _git(root, "worktree", "remove", "--force", str(base))
            _git(root, "worktree", "prune")


def l14_gate(store: Store, root: Path, against: str,
             head: list[TestCheck] | None = None) -> list[str]:
    """New untraced checks are blocking; pre-existing ones burn down (§6.6).

    Newness is head − base over the scanners' own observations. The head scan
    covers the live working tree — dirty state included, because the gate
    judges what is about to be committed. The base observation is governed by
    the base tree's own config: widening a scan glob makes previously
    unscanned tests new, deliberately — a check nothing had ever observed has
    never been judged. A renamed untraced check is one deletion plus one
    addition, and the addition still blocks: the burn-down is about untraced
    checks, and a renamed untraced check is still an untraced check."""
    root = Path(root)
    _resolve_ref(root, against)      # a garbage base ref fails whatever head holds
    if not _scanner_stacks(root):
        raise RuntimeError(
            "L14 was requested (--against) but no declared stack has a scanner "
            "role — nothing can observe this tree, and a gate that observes "
            "nothing must not pass. Declare [stacks.<name>.adapter] scanner "
            "in rqunit.toml (§6.6)")
    head = scan_tests(root) if head is None else head
    if not head:
        return []
    base_ids = _base_ids(root, against)
    trace_map = load_trace_map(root)
    violations = []
    for check in head:
        if check.id in base_ids or check.verifies or check.id in trace_map:
            continue
        violations.append(
            f"L14: new untraced test {check.id} — annotate it with its stack's "
            "`verifies` trace naming the RU it verifies, or mark it "
            "`infrastructure` (audited) — spec §6.6")
    return violations


def render_markdown(report: TraceReport) -> str:
    def section(title, items, empty):
        lines = [f"## {title}", ""]
        lines += [f"- {i}" for i in items] if items else [f"_{empty}_"]
        lines.append("")
        return lines

    out = ["# Traceability orphan reports (spec §6.6 — generated by `rqunit trace`, do not edit)",
           ""]
    # Blocking classes first, and present even when empty. They were absent
    # from this projection entirely while the JSON beside it carried them:
    # the committed, human-read half of the report omitted the only two things
    # that turn the gate red, so a reader could review it and conclude the
    # store was merely in burn-down.
    out += section(f"Broken annotations (BLOCKING: {len(report.invalid_annotations)})",
                   report.invalid_annotations,
                   "none — every annotation names an active RU")
    out += section(f"Dangling test refs (BLOCKING: {len(report.dangling_refs)})",
                   report.dangling_refs,
                   "none — every RU test ref resolves to a scanned check")
    out += section("Unverified RUs", report.unverified_rus, "none — every active RU verifiable")
    out += section(f"Untraced checks (burn-down: {len(report.untraced_checks)})",
                   report.untraced_checks,
                   "none — every check names its governor")
    out += section(f"Infrastructure bucket ({len(report.infrastructure)} — growth is the escape hatch rotting)",
                   report.infrastructure, "empty")
    out += section("Orphan manifest facts (C7)", report.orphan_facts, "none")
    out += section("Unscanned stacks (no scanner role declared — tests not observed)",
                   report.unscanned_stacks, "none — every declared stack is scanned")
    return "\n".join(out) + "\n"
