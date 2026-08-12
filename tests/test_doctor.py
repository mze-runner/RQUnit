"""`rqunit doctor` — structural health. Invariants: a healthy store reports
nothing; each detector fires on its own defect (a permanent RU git records as
deleted and never restored, unreferenced ADRs surface as notes, orphaned review
records warn, a branch behind upstream warns); findings never fail the run
unless --strict; and the activation pre-flight refuses a stale branch (the
no-ceiling answer to parallel-allocation collisions)."""

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from rqunit.cli.activate import main as activate_main
from rqunit.cli.doctor import main as doctor_main
from rqunit.doctor import branch_staleness, run as run_doctor
from rqunit.store import Store

FIXTURES = Path(__file__).parent.parent / "fixtures"
VALID = FIXTURES / "store" / "valid"


def _copy(tmp_path: Path) -> Path:
    root = tmp_path / "store"
    shutil.copytree(VALID, root)
    return root


def _kinds(root: Path) -> set[str]:
    return {f.kind for f in run_doctor(Store.load(root), root)}


def test_a_sparse_id_sequence_is_not_a_finding(tmp_path):
    """The fixture is deliberately sparse — RU-0001, RU-0002, RU-0142 — and
    that is now a normal store rather than a suspicious one: under one base
    every gap between consecutive allocations is an artefact of the alphabet,
    not evidence of anything. Whatever replaces gap detection must stay quiet
    here, or the replacement inherits the false alarm it was built to remove."""
    root = _copy(tmp_path)
    assert "lost-ru" not in _kinds(root)
    assert "dangling-review" not in _kinds(root)


def _git(root, *args):
    import subprocess
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)


def _repo(tmp_path):
    root = _copy(tmp_path)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "base")
    return root


def test_a_deleted_permanent_ru_is_reported_from_history(tmp_path):
    """An activated RU is append-only history. The usual cause of one going
    missing is an add/add merge resolved by keeping one side, and git is the
    only witness — the store itself cannot know what it used to hold."""
    root = _repo(tmp_path)
    (root / "spec" / "ru" / "RU-0142.yaml").unlink()
    _git(root, "commit", "-qam", "drop one")

    findings = [f for f in run_doctor(Store.load(root), root) if f.kind == "lost-ru"]
    assert findings and findings[0].severity == "warning"
    assert "RU-0142" in findings[0].message


def test_a_restored_ru_stops_being_reported(tmp_path):
    """The finding is a difference between history and the store, not a scar in
    history — restoring the file is a complete fix, and a warning that survives
    its own remedy is one people learn to ignore."""
    root = _repo(tmp_path)
    kept = (root / "spec" / "ru" / "RU-0142.yaml").read_text()
    (root / "spec" / "ru" / "RU-0142.yaml").unlink()
    _git(root, "commit", "-qam", "drop one")
    (root / "spec" / "ru" / "RU-0142.yaml").write_text(kept)
    _git(root, "commit", "-qam", "restore")

    assert [f for f in run_doctor(Store.load(root), root) if f.kind == "lost-ru"] == []


def test_activation_renaming_a_draft_is_not_a_loss(tmp_path):
    """Activation deletes the draft file and writes the permanent one. That is
    the single most common deletion in any store's history, and reporting it
    would make the finding pure noise from the first Gate 1 sitting."""
    root = _repo(tmp_path)
    draft = root / "spec" / "ru" / "RU-draft-01J3F8KQZ2ABCDEFGHJKMNPQRS.yaml"
    template = yaml.safe_load((root / "spec" / "ru" / "RU-0002.yaml").read_text())
    template["id"] = draft.stem
    template["status"] = "draft"
    draft.write_text(yaml.safe_dump(template, sort_keys=False, allow_unicode=True))
    _git(root, "add", "-A"); _git(root, "commit", "-qm", "draft")
    draft.unlink()
    _git(root, "commit", "-qam", "activate")

    assert [f for f in run_doctor(Store.load(root), root) if f.kind == "lost-ru"] == []


def test_a_store_outside_git_gets_no_history_finding(tmp_path):
    """Doctor is advisory; a store not under version control is a legitimate
    state (a fixture, a scratch copy), not a defect to report."""
    root = _copy(tmp_path)
    assert [f for f in run_doctor(Store.load(root), root) if f.kind == "lost-ru"] == []


def test_orphan_artifacts_surface_as_notes(tmp_path):
    root = _copy(tmp_path)
    (root / "spec" / "rationale").mkdir(exist_ok=True)
    (root / "spec" / "rationale" / "ADR-unlinked.md").write_text("# ADR-unlinked\n")
    findings = {f.kind: f for f in run_doctor(Store.load(root), root)}
    assert "ADR-unlinked" in findings["orphan-adr"].message


def test_dangling_review_records_warn(tmp_path):
    root = _copy(tmp_path)
    directory = root / "spec" / "reviews" / "RU-8888"
    directory.mkdir(parents=True)
    (directory / "20260728T090000Z-judgment.yaml").write_text(
        "ru: RU-8888\nverdict: pass\nreviewer: fixture-op\n")
    finding = next(f for f in run_doctor(Store.load(root), root)
                   if f.kind == "dangling-review")
    assert finding.severity == "warning" and "RU-8888" in finding.message
    assert "do not delete" in finding.suggestion    # records are history


# ------------------------------------------------------------ branch staleness

@pytest.fixture()
def behind_repo(tmp_path) -> Path:
    """A clone whose branch sits one commit behind its upstream."""
    origin = tmp_path / "origin"
    shutil.copytree(VALID, origin)
    run = lambda where, *a: subprocess.run(
        ["git", "-C", str(where), "-c", "user.email=t@t", "-c", "user.name=t", *a],
        check=True, capture_output=True)
    run(origin, "init", "-q")
    run(origin, "add", "-A")
    run(origin, "commit", "-qm", "init")
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(origin), str(clone)],
                   check=True, capture_output=True)
    (origin / "spec" / "NEWER.md").write_text("moved on\n")
    run(origin, "add", "-A")
    run(origin, "commit", "-qm", "ahead")
    run(clone, "fetch", "-q")
    return clone


def test_branch_behind_upstream_warns(behind_repo):
    finding = next(f for f in branch_staleness(behind_repo) if f.kind == "branch-behind")
    assert "1 commit" in finding.message
    assert "activate batch" in finding.suggestion


def test_no_upstream_is_silent(tmp_path):
    root = _copy(tmp_path)
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True, capture_output=True)
    assert branch_staleness(root) == []


def test_activation_refuses_a_stale_branch_unless_overridden(behind_repo):
    result = CliRunner().invoke(activate_main, [
        "batch", "--store", str(behind_repo), "--feature", "FEAT-billing",
        "--reviewer", "fixture-op"])
    assert result.exit_code != 0
    assert "behind its upstream" in result.output
    # the override exists and gets past the pre-flight (it then fails later for
    # unrelated reasons — the point is the staleness gate no longer blocks)
    overridden = CliRunner().invoke(activate_main, [
        "batch", "--store", str(behind_repo), "--feature", "FEAT-billing",
        "--reviewer", "fixture-op", "--allow-stale-branch"])
    assert "behind its upstream" not in overridden.output


# ------------------------------------------------------------ CLI contract

def test_findings_are_advisory_unless_strict(tmp_path):
    root = _copy(tmp_path)
    directory = root / "spec" / "reviews" / "RU-8888"
    directory.mkdir(parents=True)
    (directory / "r.yaml").write_text("ru: RU-8888\n")
    runner = CliRunner()
    assert runner.invoke(doctor_main, ["--store", str(root)]).exit_code == 0
    strict = runner.invoke(doctor_main, ["--store", str(root), "--strict"])
    assert strict.exit_code == 1
    text = runner.invoke(doctor_main, ["--store", str(root), "--format", "text"])
    assert "warning/dangling-review" in text.output


def test_history_check_survives_a_machine_without_git(tmp_path):
    """A container that ships the store but not git is an ordinary CI shape.
    Doctor is advisory: crashing there would exit 2 and take every other
    finding down with it."""
    from unittest import mock

    root = _repo(tmp_path)
    with mock.patch("rqunit.doctor.shutil.which", return_value=None):
        assert [f for f in run_doctor(Store.load(root), root) if f.kind == "lost-ru"] == []


def test_an_id_rewritten_in_place_is_not_hidden_by_rename_detection(tmp_path):
    """Rewriting an id is the act the permanence rule forbids outright. Git
    reads it as a rename by default, so the query has to be told not to follow
    renames — otherwise doctor reports a healthy store precisely when the
    unrepairable thing has happened."""
    root = _repo(tmp_path)
    ru_dir = root / "spec" / "ru"
    data = yaml.safe_load((ru_dir / "RU-0142.yaml").read_text())
    data["id"] = "RU-0143"
    (ru_dir / "RU-0143.yaml").write_text(yaml.safe_dump(data, sort_keys=False))
    (ru_dir / "RU-0142.yaml").unlink()
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "tidy an id")

    findings = [f for f in run_doctor(Store.load(root), root) if f.kind == "lost-ru"]
    assert findings and "RU-0142" in findings[0].message
