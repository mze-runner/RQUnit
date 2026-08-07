"""spec-trace (TASK-080, spec §6.6): bidirectional traceability, computed.

Forward: every non-infrastructure check carries a resolvable `verifies` trace
(`/// verifies: RU-XXXX[, RU-YYYY]` doc comment above the test attribute, or
inheritance via trace-map.json for generated suites). Backward: every RU test
ref resolves to a real check. Both directions plus orphan manifest facts (C7)
land in one report pair: spec/projections/orphans.{md,json}.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .checks.base import run_checks
from .config import load as load_config
from .errors import BadConfig
from .status import compute
from .store import Store

_TEST_ATTR = re.compile(r"^\s*#\[(?:tokio::)?test[^\]]*\]\s*$")
_FN = re.compile(r"^\s*(?:pub\s+)?(?:async\s+)?fn\s+(\w+)")
_VERIFIES = re.compile(r"^\s*///\s*verifies:\s*(.+)$")
_PACKAGE = re.compile(r'^\s*name\s*=\s*"([^"]+)"', re.MULTILINE)


@dataclass(frozen=True)
class Scanner:
    """A per-stack test scanner — the seam where language knowledge lives.

    Deliberately a registry of FUNCTIONS rather than a parameterized generic
    scanner: test discovery differs structurally between stacks (Rust's
    `#[test]` above a free fn in `tests/`; JUnit's `@Test` on a method under
    `src/test/java`), and pretending one algorithm fits both would be false
    generality. Adding a language means writing `scan`, not bending a schema.
    """

    name: str
    scan: Callable[[Path, object], list["TestCheck"]]
    definition: re.Pattern       # an added diff line that defines a test (L14)
    diff_pathspecs: Callable[[object], list[str]]


SCANNERS: dict[str, Scanner] = {}


def register(scanner: Scanner) -> Scanner:
    SCANNERS[scanner.name] = scanner
    return scanner


def _stack_configs(root: Path) -> list[tuple[Scanner, object]]:
    """Declared stacks paired with their scanner, in declaration order.
    A stack with no registered scanner contributes nothing here — its checks
    arrive via its adapter's scanner role once one is declared."""
    config = load_config(root)
    out = []
    for stack in config.stacks:
        scanner = SCANNERS.get(stack.name)
        if scanner is not None:
            out.append((scanner, stack))
    return out


@dataclass(frozen=True)
class TestCheck:
    id: str                 # package::file_stem::fn
    path: str               # repo-relative file
    fn: str
    verifies: tuple[str, ...]   # RU ids, or ("infrastructure",), or ()


def _package_name(cargo_toml: Path) -> str | None:
    m = _PACKAGE.search(cargo_toml.read_text())
    return m.group(1) if m else None


def _globs(stack, key: str, default: list[str]) -> list[str]:
    """A passthrough key this transitional in-core scanner still reads. The
    NAME is the adapter manifest's problem, but the SHAPE drives a gate here,
    so it is validated at the read site — a malformed glob list silently
    bent into pathspecs would let L14 examine nonsense and report green."""
    value = stack.options.get(key, default)
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise BadConfig("rqunit.toml",
                        f"[stacks.{stack.name}] {key} must be a list of glob strings")
    return list(value)


def scan_rust(root: Path, stack) -> list[TestCheck]:
    """Rust: `#[test]`/`#[tokio::test]` above a free fn in a crate's `tests/`.
    Which crates participate is consumer data (rqunit.toml trace_scan —
    adapter-owned, read here only until the scanner moves out of core)."""
    out: list[TestCheck] = []
    seen_dirs: set[Path] = set()
    for pattern in _globs(stack, "trace_scan", ["**/Cargo.toml"]):
        for cargo in sorted(Path(root).glob(pattern)):
            crate_dir = cargo.parent
            tests_dir = crate_dir / "tests"
            if crate_dir in seen_dirs or not tests_dir.is_dir():
                continue
            seen_dirs.add(crate_dir)
            package = _package_name(cargo)
            if not package:
                continue
            for rs in sorted(tests_dir.rglob("*.rs")):
                out.extend(_scan_file(root, package, rs))
    return out


register(Scanner(
    name="rust",
    scan=scan_rust,
    definition=_FN,
    diff_pathspecs=lambda stack: _globs(stack, "trace_diff", ["*/tests/*.rs"]),
))


def scan_tests(root: Path) -> list[TestCheck]:
    """Every configured stack's tests, merged. Check ids are stack-qualified
    already (Rust: `<package>::<file>::<fn>`), so the union never collides."""
    out: list[TestCheck] = []
    for scanner, config in _stack_configs(root):
        out.extend(scanner.scan(root, config))
    return out


def _scan_file(root: Path, package: str, rs: Path) -> list[TestCheck]:
    lines = rs.read_text().splitlines()
    out = []
    for i, line in enumerate(lines):
        if not _TEST_ATTR.match(line):
            continue
        # fn is below (possibly after further attributes)
        fn_name = None
        for j in range(i + 1, min(i + 6, len(lines))):
            m = _FN.match(lines[j])
            if m:
                fn_name = m.group(1)
                break
            if not lines[j].lstrip().startswith("#["):
                break
        if not fn_name:
            continue
        # doc comments sit above the attribute block
        verifies: list[str] = []
        k = i - 1
        while k >= 0 and (lines[k].lstrip().startswith(("///", "#["))):
            m = _VERIFIES.match(lines[k])
            if m:
                verifies = [t.strip() for t in m.group(1).split(",") if t.strip()]
            k -= 1
        out.append(TestCheck(
            id=f"{package}::{rs.stem}::{fn_name}",
            path=str(rs.relative_to(root)),
            fn=fn_name,
            verifies=tuple(verifies),
        ))
    return out


def load_trace_map(root: Path) -> dict[str, list[str]]:
    import json
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

    @property
    def blocking(self) -> list[str]:
        return self.dangling_refs + self.invalid_annotations


def build_report(store: Store, root: Path) -> TraceReport:
    report = TraceReport()
    checks = scan_tests(root)
    check_ids = {c.id for c in checks}
    trace_map = load_trace_map(root)
    active = {ru.id for ru in store.rus() if ru.status == "active"}

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
                if not re.match(r"^RU-[0-9]{4}$", ru_id):
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


def new_test_fns_in_diff(root: Path, against: str) -> list[tuple[str, str]]:
    """(file, definition) pairs ADDED relative to `against` (L14 gate), across
    every configured stack — each contributes its own pathspecs and its own
    notion of what a test definition looks like."""
    added: list[tuple[str, str]] = []
    for scanner, config in _stack_configs(root):
        pathspecs = scanner.diff_pathspecs(config)
        if not pathspecs:
            continue
        proc = subprocess.run(
            ["git", "-C", str(root), "diff", "-U0", against, "--", *pathspecs],
            capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"git diff failed: {proc.stderr.strip()}")
        current = None
        for line in proc.stdout.splitlines():
            if line.startswith("+++ b/"):
                current = line[6:]
            elif line.startswith("+") and current:
                m = scanner.definition.match(line[1:])
                if m:
                    added.append((current, m.group(1)))
    return added


def l14_gate(store: Store, root: Path, against: str) -> list[str]:
    """New untraced checks are blocking; pre-existing ones burn down (§6.6)."""
    added = new_test_fns_in_diff(root, against)
    if not added:
        return []
    checks = scan_tests(root)
    trace_map = load_trace_map(root)
    by_key = {(c.path, c.fn): c for c in checks}
    violations = []
    for file, fn in added:
        check = by_key.get((file, fn))
        if check is None:
            continue  # helper fn, not a test
        if check.verifies or check.id in trace_map:
            continue
        violations.append(
            f"L14: new untraced test {check.id} — add `/// verifies: RU-XXXX` "
            "(or `/// verifies: infrastructure`, audited) above the test attribute")
    return violations


def render_markdown(report: TraceReport) -> str:
    def section(title, items, empty):
        lines = [f"## {title}", ""]
        lines += [f"- {i}" for i in items] if items else [f"_{empty}_"]
        lines.append("")
        return lines

    out = ["# Traceability orphan reports (spec §6.6 — generated by spec-trace, do not edit)", ""]
    out += section("Unverified RUs", report.unverified_rus, "none — every active RU verifiable")
    out += section(f"Untraced checks (burn-down: {len(report.untraced_checks)})",
                   report.untraced_checks,
                   "none — every check names its governor")
    out += section(f"Infrastructure bucket ({len(report.infrastructure)} — growth is the escape hatch rotting)",
                   report.infrastructure, "empty")
    out += section("Orphan manifest facts (C7)", report.orphan_facts, "none")
    return "\n".join(out) + "\n"
