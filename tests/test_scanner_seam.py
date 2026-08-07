"""Scanner seam (Phase II, item 3) — where per-language test discovery plugs in.

Invariants: the registry drives both scanning and the L14 diff gate; only
configured stacks run; a second stack merges without touching core; and the
Rust scanner still finds exactly what it found before the seam existed."""

import shutil
import subprocess
from pathlib import Path

import pytest

from rqunit import trace
from rqunit.trace import SCANNERS, Scanner, l14_gate, scan_tests

FIXTURES = Path(__file__).parent.parent / "fixtures"
RUSTTREE = FIXTURES / "rusttree"


def test_rust_is_registered_and_carries_its_own_language_knowledge():
    rust = SCANNERS["rust"]
    assert rust.name == "rust"
    assert rust.definition.match("    async fn some_test() {")     # Rust fn shapes
    assert not rust.definition.match("    public void someTest() {")  # not JUnit's


def test_scanning_goes_through_the_registry(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    shutil.copytree(RUSTTREE, root)
    assert scan_tests(root), "baseline: the rust scanner finds the fixture's tests"

    calls: list[Path] = []

    def fake(scan_root, config):
        calls.append(scan_root)
        return []

    monkeypatch.setitem(SCANNERS, "rust", Scanner(
        name="rust", scan=fake, definition=SCANNERS["rust"].definition,
        diff_pathspecs=lambda c: list(c.options.get("trace_diff", []))))
    assert scan_tests(root) == []
    assert calls == [root]          # core delegates, never scans on its own


def test_only_declared_stacks_run(tmp_path, monkeypatch):
    """A registered scanner whose stack is not declared stays dormant —
    adding a language to the product must not change existing consumers."""
    root = tmp_path / "repo"
    shutil.copytree(RUSTTREE, root)
    ran: list[str] = []

    monkeypatch.setitem(SCANNERS, "java", Scanner(
        name="java", scan=lambda r, c: ran.append("java") or [],
        definition=SCANNERS["rust"].definition, diff_pathspecs=lambda c: []))
    scan_tests(root)
    assert ran == []                # no [stacks.java] table → skipped


def test_a_second_stack_merges_without_core_changes(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    shutil.copytree(RUSTTREE, root)
    before = {c.id for c in scan_tests(root)}

    extra = trace.TestCheck(id="svc::PaymentTest::refunds", path="src/test/java/PaymentTest.java",
                      fn="refunds", verifies=("RU-0001",))

    from rqunit.config import Config, Stack
    fake = Config(stacks=(*trace.load_config(root).stacks, Stack(name="java")))
    monkeypatch.setattr(trace, "load_config", lambda r: fake)
    monkeypatch.setitem(SCANNERS, "java", Scanner(
        name="java", scan=lambda r, c: [extra],
        definition=SCANNERS["rust"].definition, diff_pathspecs=lambda c: []))

    merged = {c.id for c in scan_tests(root)}
    assert merged == before | {extra.id}     # union, no collision, no core edit


@pytest.fixture()
def tree_repo(tmp_path) -> Path:
    root = tmp_path / "repo"
    shutil.copytree(RUSTTREE, root)
    run = lambda *a: subprocess.run(["git", "-C", str(root), *a], check=True, capture_output=True)
    run("init", "-q")
    run("-c", "user.email=t@t", "-c", "user.name=t", "add", "-A")
    run("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
    return root


def test_l14_gate_uses_each_stacks_own_definition_pattern(tree_repo):
    tests = tree_repo / "service-x" / "tests" / "sample_tests.rs"
    tests.write_text(tests.read_text() + "\n#[test]\nfn fresh_and_untraced() {}\n")
    violations = l14_gate(None, tree_repo, "HEAD")
    assert len(violations) == 1 and "fresh_and_untraced" in violations[0]


def test_l14_skips_stacks_with_no_pathspecs(tree_repo, monkeypatch):
    monkeypatch.setitem(SCANNERS, "rust", Scanner(
        name="rust", scan=SCANNERS["rust"].scan, definition=SCANNERS["rust"].definition,
        diff_pathspecs=lambda c: []))
    tests = tree_repo / "service-x" / "tests" / "sample_tests.rs"
    tests.write_text(tests.read_text() + "\n#[test]\nfn fresh_and_untraced() {}\n")
    assert l14_gate(None, tree_repo, "HEAD") == []
