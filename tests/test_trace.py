"""Traceability acceptance: scanned observations, the three orphan classes,
the report, and the L14 gate (a new untraced test blocks; a pre-existing one
is burn-down).

Runs against fixture stores. `store/traced` is a store paired with a committed
scanner observation whose check ids match its RU verification refs — the
arrangement a real consumer has, reproduced small enough to reason about.
Deep parsing semantics (attribute stacks, tokio tests, doc-comment
annotations) are the Rust adapter's own tests' business; here the artifact is
the interface, and edits to it are how a tree's tests "change"."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from rqunit.store import Store
from rqunit.trace import build_report, l14_gate, render_markdown, scan_tests

FIXTURES = Path(__file__).parent.parent / "fixtures"
# Core-owned: the seam under test is artifact-shaped observation, not Rust
# parsing — the adapter's kit tree is the adapter's to grow.
RUSTTREE = Path(__file__).parent.parent / "fixtures" / "scanned-tree"
TRACED = FIXTURES / "store" / "traced"


def _amend_checks(root: Path, add=None, clear=False):
    path = root / "scanned-checks.json"
    data = json.loads(path.read_text())
    if clear:
        data["checks"] = []
    for check in add or []:
        data["checks"].append(check)
    path.write_text(json.dumps(data))


def _check(package_file, fn, verifies):
    package, file = package_file
    return {"id": f"{package}::{Path(file).stem}::{fn}", "path": file,
            "fn": fn, "verifies": verifies}


ITEST = ("itest", "itest/tests/orders.rs")
SAMPLE = ("service-x-application", "service-x/tests/sample_tests.rs")


# ------------------------------------------------------------ observations

def test_scanned_observations_round_trip_annotations_attrs_and_helpers():
    checks = {c.fn: c for c in scan_tests(RUSTTREE)}
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
    _amend_checks(root, clear=True)             # every check removed
    report = build_report(Store.load(root), root)
    assert report.dangling_refs and "cancellation_latency_bound" in report.dangling_refs[0]


def test_annotations_must_target_active_rus(tmp_path):
    root = tmp_path / "store"
    shutil.copytree(TRACED, root)
    assert build_report(Store.load(root), root).invalid_annotations == []

    _amend_checks(root, add=[_check(ITEST, "ghost", ["RU-9999"])])
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
                    "Orphan manifest facts", "Unscanned stacks"):
        assert heading in md


def test_a_declared_stack_without_a_scanner_is_reported_not_skipped(tmp_path):
    root = tmp_path / "store"
    shutil.copytree(TRACED, root)
    toml = root / "rqunit.toml"
    toml.write_text(toml.read_text() + "\n[stacks.jvm]\n")
    report = build_report(Store.load(root), root)
    assert report.unscanned_stacks == ["jvm"]
    assert report.blocking == []                        # a capability gap, not an error


# ------------------------------------------------------------ L14 gate

@pytest.fixture()
def tree_repo(tmp_path) -> Path:
    root = tmp_path / "repo"
    shutil.copytree(RUSTTREE, root)
    run = lambda *a: subprocess.run(["git", "-C", str(root), *a], check=True, capture_output=True)
    run("init", "-q")
    run("-c", "user.email=t@t", "-c", "user.name=t", "add", "-A")
    run("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
    return root


def test_l14_blocks_newly_observed_untraced_tests_only(tree_repo):
    """Set difference: an id in head's observation but not base's is new —
    whether it was just written or a widened scan just started observing it.
    A check nothing had ever observed has never been judged."""
    _amend_checks(tree_repo, add=[_check(SAMPLE, "fresh_and_untraced", [])])
    violations = l14_gate(None, tree_repo, "HEAD")
    assert len(violations) == 1 and "fresh_and_untraced" in violations[0]
    # pre-existing untraced test (untraced_with_extra_attr) never blocks
    assert not any("untraced_with_extra_attr" in v for v in violations)


def test_l14_accepts_new_traced_and_infrastructure_tests(tree_repo):
    _amend_checks(tree_repo, add=[
        _check(SAMPLE, "fresh_traced", ["RU-0001"]),
        _check(SAMPLE, "fresh_probe", ["infrastructure"]),
    ])
    assert l14_gate(None, tree_repo, "HEAD") == []


def test_l14_flags_a_renamed_untraced_check(tree_repo):
    """A rename is one deletion plus one addition, and the addition still
    blocks: a renamed untraced check is still an untraced check."""
    path = tree_repo / "scanned-checks.json"
    data = json.loads(path.read_text())
    for check in data["checks"]:
        if check["fn"] == "untraced_with_extra_attr":
            check["fn"] = "untraced_renamed"
            check["id"] = "service-x-application::sample_tests::untraced_renamed"
    path.write_text(json.dumps(data))
    violations = l14_gate(None, tree_repo, "HEAD")
    assert len(violations) == 1 and "untraced_renamed" in violations[0]


def test_l14_ignores_a_reformatted_tree_because_identity_survives(tree_repo):
    """The observation is identity, not text: touching the source without
    changing any check id yields an empty set difference."""
    tests = tree_repo / "service-x" / "tests" / "sample_tests.rs"
    tests.write_text(tests.read_text().replace("\n\n", "\n\n\n"))
    assert l14_gate(None, tree_repo, "HEAD") == []


def test_l14_rejects_an_unresolvable_ref(tree_repo):
    with pytest.raises(RuntimeError) as caught:
        l14_gate(None, tree_repo, "no-such-ref")
    assert "no-such-ref" in str(caught.value)
