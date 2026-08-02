"""`rqunit doctor` — structural health. Invariants: a healthy store reports
nothing; each detector fires on its own defect (lost RU leaves an id gap,
unreferenced ADRs surface as notes, orphaned review records warn, a
branch behind upstream warns); findings never fail the run unless --strict;
and the activation pre-flight refuses a stale branch (the no-ceiling answer
to parallel-allocation collisions)."""

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


def test_consecutive_ids_and_intact_reviews_report_nothing(tmp_path):
    root = _copy(tmp_path)
    # The fixture is deliberately sparse (RU-0001, 0002, 0142) to exercise
    # unrelated features; drop the outlier so ids are consecutive.
    (root / "spec" / "ru" / "RU-0142.yaml").unlink()
    assert "id-gap" not in _kinds(root)
    assert "dangling-review" not in _kinds(root)


def test_id_gap_detects_a_lost_ru(tmp_path):
    root = _copy(tmp_path)
    ru_dir = root / "spec" / "ru"
    template = yaml.safe_load((ru_dir / "RU-0002.yaml").read_text())
    for number in (3, 5):                       # deliberately skip RU-0004
        template["id"] = f"RU-{number:04d}"
        (ru_dir / f"RU-{number:04d}.yaml").write_text(
            yaml.safe_dump(template, sort_keys=False, allow_unicode=True))
    findings = [f for f in run_doctor(Store.load(root), root) if f.kind == "id-gap"]
    assert len(findings) == 1
    assert "RU-0004" in findings[0].message and findings[0].severity == "warning"


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
