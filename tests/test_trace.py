"""Traceability acceptance: scanner semantics, the three orphan classes, the
report, and the L14 diff gate (a new untraced test blocks; a pre-existing one
is burn-down).

Runs against fixture stores. `store/traced` is a store paired with a companion
test crate whose check ids match its RU verification refs — the arrangement a
real consumer has, reproduced small enough to reason about."""

import shutil
import subprocess
from pathlib import Path

import pytest

from rqunit.store import Store
from rqunit.trace import build_report, l14_gate, render_markdown, scan_tests

FIXTURES = Path(__file__).parent.parent / "fixtures"
TRACED = FIXTURES / "store" / "traced"


# ------------------------------------------------------------ scanner

def test_scanner_parses_annotations_attrs_and_skips_helpers():
    checks = {c.fn: c for c in scan_tests(FIXTURES / "rusttree")}
    assert set(checks) == {"traced_single", "traced_multi", "plumbing_probe",
                           "untraced_with_extra_attr", "traced_to_missing_ru"}
    assert checks["traced_single"].verifies == ("RU-0001",)
    assert checks["traced_multi"].verifies == ("RU-0001", "RU-0002")   # tokio + multi-RU
    assert checks["plumbing_probe"].verifies == ("infrastructure",)
    assert checks["untraced_with_extra_attr"].verifies == ()           # attr stack handled
    assert checks["traced_single"].id == "service-x-application::sample_tests::traced_single"


# ------------------------------------------------------------ report semantics

def test_resolved_test_refs_leave_no_dangling_entries():
    report = build_report(Store.load(TRACED), TRACED)
    assert report.dangling_refs == []


def test_a_ref_naming_no_scanned_test_is_dangling(tmp_path):
    root = tmp_path / "store"
    shutil.copytree(TRACED, root)
    (root / "itest" / "tests" / "orders.rs").write_text("// every check removed\n")
    report = build_report(Store.load(root), root)
    assert report.dangling_refs and "cancellation_latency_bound" in report.dangling_refs[0]


def test_annotations_must_target_active_rus(tmp_path):
    root = tmp_path / "store"
    shutil.copytree(TRACED, root)
    assert build_report(Store.load(root), root).invalid_annotations == []

    tests = root / "itest" / "tests" / "orders.rs"
    tests.write_text(tests.read_text() + "\n/// verifies: RU-9999\n#[test]\nfn ghost() {}\n")
    report = build_report(Store.load(root), root)
    assert any("RU-9999" in entry for entry in report.invalid_annotations)


def test_unverified_rus_carry_a_computed_reason_and_are_active():
    # Invariant, not a pinned id list: every unverified entry names an ACTIVE
    # RU and states a computed reason.
    store = Store.load(TRACED)
    active = {ru.id for ru in store.rus() if ru.status == "active"}
    for entry in build_report(store, TRACED).unverified_rus:
        ru_id, _, reason = entry.partition(":")
        assert ru_id in active, entry
        assert "blocked" in reason or "failing" in reason, entry


def test_infrastructure_is_an_audited_bucket_disjoint_from_the_burndown():
    report = build_report(Store.load(TRACED), TRACED)
    assert report.infrastructure                       # the escape hatch exists
    assert report.untraced_checks                      # and burn-down is separate
    assert not (set(report.infrastructure) & set(report.untraced_checks))


def test_orphan_facts_mirror_c7():
    # Structural only — the count is a consumer's burn-down and must be free to
    # fall to zero without breaking a test.
    report = build_report(Store.load(TRACED), TRACED)
    assert all("orphan fact" in entry for entry in report.orphan_facts)


def test_markdown_report_renders_all_sections():
    md = render_markdown(build_report(Store.load(TRACED), TRACED))
    for heading in ("Unverified RUs", "Untraced checks", "Infrastructure bucket",
                    "Orphan manifest facts"):
        assert heading in md


# ------------------------------------------------------------ L14 diff gate

@pytest.fixture()
def tree_repo(tmp_path) -> Path:
    root = tmp_path / "repo"
    shutil.copytree(FIXTURES / "rusttree", root)
    run = lambda *a: subprocess.run(["git", "-C", str(root), *a], check=True, capture_output=True)
    run("init", "-q")
    run("-c", "user.email=t@t", "-c", "user.name=t", "add", "-A")
    run("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
    return root


def test_l14_blocks_new_untraced_tests_only(tree_repo):
    tests = tree_repo / "service-x" / "tests" / "sample_tests.rs"
    tests.write_text(tests.read_text() + "\n#[test]\nfn fresh_and_untraced() {}\n")
    violations = l14_gate(None, tree_repo, "HEAD")
    assert len(violations) == 1 and "fresh_and_untraced" in violations[0]
    # pre-existing untraced test (untraced_with_extra_attr) never blocks
    assert not any("untraced_with_extra_attr" in v for v in violations)


def test_l14_accepts_new_traced_and_infrastructure_tests(tree_repo):
    tests = tree_repo / "service-x" / "tests" / "sample_tests.rs"
    tests.write_text(tests.read_text()
                     + "\n/// verifies: RU-0001\n#[test]\nfn fresh_traced() {}\n"
                     + "\n/// verifies: infrastructure\n#[test]\nfn fresh_probe() {}\n")
    assert l14_gate(None, tree_repo, "HEAD") == []
