"""Phase 4 acceptance: canonicalizer, status engine, impact reporter,
spec-activate (atomicity, refusals, crash injection, concurrent allocation),
spec-review (records, reviewed computation, append-only guard)."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from rqunit.canonical import canonical_hash
from rqunit.cli.activate import main as activate_cli
from rqunit.cli.review import main as review_cli
from rqunit.impact import build_report, diff_manifests
from rqunit.status import compute
from rqunit.store import Store

FIXTURES = Path(__file__).parent.parent / "fixtures"
ULID_A = "01K1TESTAAAA000000000000AA"
ULID_B = "01K1TESTBBBB000000000000BB"


def _git(root: Path, *args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=False)


@pytest.fixture()
def repo(tmp_path) -> Path:
    root = tmp_path / "repo"
    shutil.copytree(FIXTURES / "store" / "activation", root)
    # framework schemas load from the real repo (D-P1.6) — only content is copied
    _git(root, "init", "-q")
    _git(root, "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A")
    _git(root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
    return root


def _commits(root: Path) -> int:
    return int(_git(root, "rev-list", "--count", "HEAD").stdout.strip())


# ------------------------------------------------------------ canonicalizer

def test_canonical_hash_is_key_order_invariant_and_tier_defaulted():
    a = {"statement": "s", "scope": {"owns": ["x"]}, "verification": [{"type": "test", "ref": "t"}]}
    b = {"verification": [{"ref": "t", "type": "test"}], "scope": {"owns": ["x"]},
         "statement": "s", "tier": "standard", "tags": ["ignored"], "id": "ignored"}
    assert canonical_hash(a) == canonical_hash(b)
    assert canonical_hash({**a, "statement": "s2"}) != canonical_hash(a)


# ------------------------------------------------------------ status engine

def test_status_engine_computes_the_four_states():
    store = Store.load(FIXTURES / "store" / "status")
    by_id = {ru.id: ru for ru in store.rus()}
    human = compute(store, by_id["RU-0001"])
    assert human.done and human.reviewed and human.debt
    todo = compute(store, by_id["RU-0002"])
    assert todo.blocked and not todo.done
    stale = compute(store, by_id["RU-0003"])
    assert stale.failing and not stale.done


# ------------------------------------------------------------ impact reporter

def test_impact_classifies_and_lists_affected_rus():
    store = Store.load(FIXTURES / "store" / "valid")
    manifest = store.manifests()["service-orders"]
    old = yaml.safe_load(manifest.path.read_text())
    new = yaml.safe_load(manifest.path.read_text())
    new["values"]["retention"]["decision_log_days"] = 30          # mutating
    new["endpoints"].append({"id": "new_ep", "method": "GET", "path": "/api/v1/new",
                             "access": "public", "ru": "FEAT-order-cancellation"})  # additive
    changes = diff_manifests(old, new)
    kinds = {(c.kind, c.section, c.key) for c in changes}
    assert ("mutating", "values", "retention.decision_log_days") in kinds
    assert ("additive", "endpoints", "new_ep") in kinds
    # affected-RU listing needs a store whose RU references the key
    report = build_report(store, "service-orders",
                          [c for c in changes if c.kind == "mutating"])
    assert report.mutating and isinstance(report.affected_rus, dict)


# ------------------------------------------------------------ spec-activate

def test_activation_happy_path_is_atomic_and_stamped(repo):
    result = CliRunner().invoke(activate_cli, [
        "batch", "--store", str(repo), "--feature", "FEAT-pilot", "--reviewer", "test-op"])
    assert result.exit_code == 0, result.output
    store = Store.load(repo)
    ids = [ru.id for ru in store.rus()]
    assert ids == ["RU-0100", "RU-0101", "RU-0102"]
    by_id = {ru.id: ru for ru in store.rus()}
    assert by_id["RU-0100"].status == "superseded"                 # supersedes target flipped
    a = by_id["RU-0101"]
    assert a.raw["draft_id"] == f"RU-draft-{ULID_A}"
    assert a.raw["gate1_stamp"]["hash"] == canonical_hash(a.raw)   # valid stamp
    assert a.raw["link_fingerprints"]["RU-0100"]                   # fingerprinted edge
    b = by_id["RU-0102"]
    assert "RU-0101" in b.raw["statement"] and "RU-draft-" not in b.raw["statement"]  # cross-ref rewrite
    assert _commits(repo) == 2                                     # exactly ONE activation commit
    # projections regenerate inside the activation (a pre-commit spec-generate
    # check gate must see them current, not stale against the renamed RUs)
    index = (repo / "spec" / "projections" / "ru-index.json").read_text()
    assert "RU-0101" in index and "RU-draft-" not in index


def test_activation_crash_between_rename_and_rewrite_commits_nothing(repo):
    env_backup = os.environ.get("SPEC_TOOLS_CRASH")
    os.environ["SPEC_TOOLS_CRASH"] = "post-rename"
    try:
        result = CliRunner().invoke(activate_cli, [
            "batch", "--store", str(repo), "--feature", "FEAT-pilot", "--reviewer", "test-op"])
    finally:
        if env_backup is None:
            os.environ.pop("SPEC_TOOLS_CRASH", None)
        else:
            os.environ["SPEC_TOOLS_CRASH"] = env_backup
    assert result.exit_code == 1
    assert _commits(repo) == 1                                     # no partial commit
    assert _git(repo, "status", "--porcelain").stdout.strip()      # tree dirty but restorable


def test_activation_refuses_a_red_store(repo):
    ru = repo / "spec" / "ru" / "RU-0100.yaml"
    raw = yaml.safe_load(ru.read_text())
    raw["tags"] = ["not-in-vocabulary"]
    ru.write_text(yaml.safe_dump(raw, sort_keys=False))
    result = CliRunner().invoke(activate_cli, [
        "batch", "--store", str(repo), "--feature", "FEAT-pilot", "--reviewer", "test-op"])
    assert result.exit_code == 1 and "store is red" in result.output


def test_activation_batches_are_all_or_nothing(repo):
    result = CliRunner().invoke(activate_cli, [
        "batch", "--store", str(repo), "--drafts", f"RU-draft-{ULID_A}",
        "--drafts", "RU-draft-01K1TESTCCCC000000000000CC", "--reviewer", "test-op"])
    assert result.exit_code == 1 and "all-or-nothing" in result.output
    assert not list((repo / "spec" / "ru").glob("RU-0101*"))       # nothing activated


def test_activation_blocks_under_covered_drafts(repo):
    # The shipped seed policy is the one a fresh consumer gets, so exercising
    # activation against it also proves the seed is coherent.
    from rqunit.schemas import SEED_DIR
    shutil.copy(SEED_DIR / "coverage.policy.yaml",
                repo / "spec" / "framework" / "coverage.policy.yaml")
    ru = repo / "spec" / "ru" / f"RU-draft-{ULID_B}.yaml"
    raw = yaml.safe_load(ru.read_text())
    raw["tags"] = ["security"]                                     # requires contract AND test
    ru.write_text(yaml.safe_dump(raw, sort_keys=False))
    result = CliRunner().invoke(activate_cli, [
        "batch", "--store", str(repo), "--feature", "FEAT-pilot", "--reviewer", "test-op"])
    assert result.exit_code == 1 and "coverage policy" in result.output


def test_concurrent_activation_conflicts_at_merge_by_design(repo, tmp_path):
    clone = tmp_path / "clone"
    shutil.copytree(repo, clone)
    for root in (repo, clone):
        result = CliRunner().invoke(activate_cli, [
            "batch", "--store", str(root), "--feature", "FEAT-pilot", "--reviewer", "test-op"])
        assert result.exit_code == 0, result.output
    ids = lambda r: sorted(p.name for p in (r / "spec" / "ru").glob("RU-01*.yaml"))
    assert ids(repo) == ids(clone)  # same ids allocated → merge conflict, documented not "fixed"


# ------------------------------------------------------------ spec-review

def test_review_record_flips_reviewed_and_never_carries_over(repo):
    CliRunner().invoke(activate_cli, [
        "batch", "--store", str(repo), "--feature", "FEAT-pilot", "--reviewer", "test-op"])
    # give RU-0101 a human criterion by supersession? No — records attach as-is:
    store = Store.load(repo)
    ru = next(r for r in store.rus() if r.id == "RU-0101")
    assert compute(store, ru).reviewed                             # no human entries → stamp suffices
    result = CliRunner().invoke(review_cli, [
        "record", "RU-0101", "--store", str(repo), "--verdict", "pass",
        "--criterion", "Does the retention window satisfy the auditor?",
        "--reviewer", "test-op", "--packet", "TASK-0001"])
    assert result.exit_code == 0, result.output
    assert list((repo / "spec" / "reviews" / "RU-0101").glob("*.yaml"))


def test_review_guard_rejects_tampering(repo):
    CliRunner().invoke(review_cli, [
        "record", "RU-0100", "--store", str(repo), "--verdict", "pass",
        "--criterion", "Is the audit window sufficient for compliance?", "--reviewer", "op"])
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "record")
    ok = CliRunner().invoke(review_cli, ["guard", "--store", str(repo), "--against", "HEAD~1"])
    assert ok.exit_code == 0
    record = next((repo / "spec" / "reviews" / "RU-0100").glob("*.yaml"))
    record.write_text(record.read_text().replace("verdict: pass", "verdict: fail"))
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "tamper")
    # The guard catches tampering with records that EXISTED at the base ref
    # (a record added and edited within the same range diffs as an addition).
    bad = CliRunner().invoke(review_cli, ["guard", "--store", str(repo), "--against", "HEAD~1"])
    assert bad.exit_code == 1


def test_reviewer_ids_reject_contact_info(repo):
    """Operator ids are handles, never emails (formats §9 v0.10.1) — the store
    is published with the repository."""
    for args in (
        ["batch", "--store", str(repo), "--feature", "FEAT-pilot", "--reviewer", "me@example.com"],
        ["restamp", "--store", str(repo), "--reviewer", "me@example.com"],
    ):
        result = CliRunner().invoke(activate_cli, args)
        assert result.exit_code == 1 and "handle" in result.output
    result = CliRunner().invoke(review_cli, [
        "record", "RU-0100", "--store", str(repo), "--verdict", "pass",
        "--criterion", "Is the audit window sufficient for compliance?",
        "--reviewer", "me@example.com"])
    assert result.exit_code == 1 and "handle" in result.output


def test_simulation_refuses_post_activation_conflicts_before_writing(repo):
    """C1/C2/C3 skip drafts by design, so a conflict that only exists once the
    draft turns active must be caught by the SIMULATED post-activation store —
    with zero files written (reproduced live at the first Gate 1 sitting)."""
    (repo / "spec" / "ru" / "RU-0098.yaml").write_text(yaml.safe_dump({
        "id": "RU-0098",
        "statement": "When a user cancels an order, the system shall halt fulfilment for the order.",
        "syntax": "ears", "status": "active", "source_ref": "INT-0001#L1-2",
        "verification": [{"type": "contract", "ref": "CT-base"}],
        "scope": {"owns": ["service-orders/fulfilment"]}, "tags": ["orders"],
    }, sort_keys=False))
    from rqunit.canonical import canonical_hash
    raw = yaml.safe_load((repo / "spec" / "ru" / "RU-0098.yaml").read_text())
    raw["gate1_stamp"] = {"hash": canonical_hash(raw), "by": "fixture-op",
                          "at": "2026-07-25T10:00:00+00:00"}
    (repo / "spec" / "ru" / "RU-0098.yaml").write_text(yaml.safe_dump(raw, sort_keys=False))
    conflicting = "RU-draft-01K1TESTDDDD000000000000DD"
    (repo / "spec" / "ru" / f"{conflicting}.yaml").write_text(yaml.safe_dump({
        "id": conflicting,
        "statement": "When a user cancels an order, the system shall continue fulfilment until shipment completes.",
        "syntax": "ears", "status": "draft", "feature": "FEAT-pilot",
        "source_ref": "INT-0001#L1-2",
        "verification": [{"type": "contract", "ref": "CT-base"}],
        "scope": {"owns": ["service-orders/fulfilment"]}, "tags": ["orders"],
    }, sort_keys=False))
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "setup")
    result = CliRunner().invoke(activate_cli, [
        "batch", "--store", str(repo), "--feature", "FEAT-pilot", "--reviewer", "test-op"])
    assert result.exit_code == 1 and "simulated POST-activation" in result.output
    assert "C1" in result.output
    assert (repo / "spec" / "ru" / f"{conflicting}.yaml").exists()   # nothing written
    assert not list((repo / "spec" / "ru").glob("RU-0101*"))
    assert _git(repo, "status", "--porcelain").stdout.strip() == ""  # tree untouched


def test_refused_commit_rolls_back_every_written_file(repo):
    """A commit gate refusing the activation must leave the store EXACTLY as
    before the run — files restored, nothing staged, no commit."""
    hooks = repo / "hooks"
    hooks.mkdir()
    hook = hooks / "pre-commit"
    hook.write_text("#!/bin/sh\necho 'gate says no' >&2\nexit 1\n")
    hook.chmod(0o755)
    _git(repo, "config", "core.hooksPath", "hooks")
    before = _git(repo, "status", "--porcelain").stdout
    result = CliRunner().invoke(activate_cli, [
        "batch", "--store", str(repo), "--feature", "FEAT-pilot", "--reviewer", "test-op"])
    assert result.exit_code == 1 and "rolled" in result.output and "gate says no" in result.output
    assert _commits(repo) == 1                                       # no commit landed
    assert (repo / "spec" / "ru" / f"RU-draft-{ULID_A}.yaml").exists()  # drafts restored
    assert not list((repo / "spec" / "ru").glob("RU-0101*"))
    assert _git(repo, "status", "--porcelain").stdout == before      # byte-identical state
