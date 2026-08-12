"""The check-evidence ledger (§6.8).

Invariants: the probe reports outcomes and the FRAMEWORK decides which is a
first; only firsts are recorded, so a ledger does not grow with every CI run
saying the same thing; a check with no evidence is never reported (absence of
evidence is not evidence of absence); and L26 stays finding-class, because a
check may legitimately never have been observed red and blocking that would
reward theatrical failures.
"""

import json
import shutil
import sys
from pathlib import Path

import pytest

from click.testing import CliRunner

from rqunit.cli.evidence import main as evidence_main
from rqunit.errors import BadConfig
from rqunit.evidence import fold, ledger_path, load_ledger, never_red, recorded
from rqunit.lints.base import run_lints
from rqunit.store import Store

FIXTURES = Path(__file__).parent.parent / "fixtures"
L26 = FIXTURES / "lints" / "L26"


def _artifact(*pairs) -> dict:
    return {"contract_version": 1, "generated_by": "fake-runner 0.1",
            "observations": [{"check_id": c, "outcome": o} for c, o in pairs]}


def _store(tmp_path: Path, kind: str = "pass") -> Path:
    root = tmp_path / "store"
    shutil.copytree(L26 / kind, root)
    return root


# ------------------------------------------------------------ the fold

def test_only_firsts_are_recorded(tmp_path):
    """The ledger records what has been DEMONSTRATED. A second red proves
    nothing a first red did not, and recording it would make an append-only
    file grow with every CI run while saying the same thing."""
    root = _store(tmp_path)
    check = "svc::orders::rejects_cancel_after_ship"       # already red and green
    fresh = fold(root, _artifact((check, "failed"), (check, "passed")),
                 at="2026-02-01T00:00:00+00:00", source="run")
    assert fresh == []


def test_a_run_repeating_one_check_records_it_once(tmp_path):
    root = _store(tmp_path)
    fresh = fold(root, _artifact(("svc::orders::records_reason", "passed"),
                                 ("svc::orders::records_reason", "passed")),
                 at="2026-02-01T00:00:00+00:00", source="run")
    assert [o.observation for o in fresh] == ["first_green"]


def test_a_later_red_is_recorded_for_a_check_only_ever_green(tmp_path):
    """The transition this whole feature exists to notice."""
    root = _store(tmp_path, "fail")
    check = "svc::orders::records_reason"
    assert check in never_red(root)
    fresh = fold(root, _artifact((check, "failed")),
                 at="2026-02-01T00:00:00+00:00", source="run")
    assert [(o.check_id, o.observation) for o in fresh] == [(check, "first_red")]


def test_never_red_excludes_checks_with_no_evidence_at_all(tmp_path):
    """Absence of evidence is not evidence of absence: a store that has never
    recorded a run must not light up entirely."""
    root = _store(tmp_path)
    assert "svc::orders::records_reason" not in recorded(root)
    assert never_red(root) == set()


def test_a_malformed_ledger_line_is_an_error_not_a_shrug(tmp_path):
    root = _store(tmp_path)
    ledger_path(root).write_text('{"check_id": "x", "observation": "maybe"}\n')
    with pytest.raises(BadConfig) as caught:
        load_ledger(root)
    assert "first_green" in str(caught.value)


# ------------------------------------------------------------ the command

def test_record_folds_an_artifact_and_appends_only_firsts(tmp_path):
    root = _store(tmp_path, "fail")
    run = tmp_path / "run.json"
    run.write_text(json.dumps(_artifact(
        ("svc::orders::records_reason", "failed"),            # new first_red
        ("svc::orders::rejects_missing_reason", "passed"))))  # already known
    before = len(load_ledger(root))

    result = CliRunner().invoke(evidence_main, ["record", "--store", str(root),
                                                "--from", str(run)])
    assert result.exit_code == 0, result.output
    after = load_ledger(root)
    assert len(after) == before + 1
    assert after[-1].observation == "first_red"
    assert after[-1].at and after[-1].source.endswith("run.json")
    # the ledger is append-only: earlier lines are untouched
    assert [o.check_id for o in after[:before]] == [
        o.check_id for o in load_ledger(root)[:before]]


def test_record_runs_a_declared_cmd_mode_probe(tmp_path):
    root = _store(tmp_path, "fail")
    probe = tmp_path / "probe.py"
    probe.write_text("import json\nprint(json.dumps(%r))"
                     % _artifact(("svc::orders::records_reason", "failed")))
    (root / "rqunit.toml").write_text(
        "[stacks.rust.adapter]\n"
        f'evidence = {{ cmd = ["{sys.executable}", "{probe}"] }}\n')
    result = CliRunner().invoke(evidence_main, ["record", "--store", str(root)])
    assert result.exit_code == 0, result.output
    assert "first_red: svc::orders::records_reason" in result.output


def test_record_without_a_probe_or_artifact_is_a_tool_error(tmp_path):
    root = _store(tmp_path)
    result = CliRunner().invoke(evidence_main, ["record", "--store", str(root)])
    assert result.exit_code == 2 and "evidence" in result.output


def test_a_probe_emitting_a_bad_outcome_is_rejected(tmp_path):
    root = _store(tmp_path)
    run = tmp_path / "run.json"
    run.write_text(json.dumps({"contract_version": 1, "generated_by": "x",
                               "observations": [{"check_id": "a", "outcome": "flaky"}]}))
    result = CliRunner().invoke(evidence_main, ["record", "--store", str(root),
                                                "--from", str(run)])
    assert result.exit_code == 2 and "check-evidence contract" in result.output


# ------------------------------------------------------------ L26

def _l26(root: Path):
    return [v for v in run_lints(Store.load(root), only="L26") if v.rule == "L26"]


@pytest.fixture()
def fail_store(tmp_path) -> Path:
    """A COPY. `rqunit evidence record` appends to a real ledger, so a test
    reading the committed fixture in place is one stray command away from a
    fixture that no longer means what it says — which happened."""
    return _store(tmp_path, "fail")


def test_l26_reports_only_checks_green_and_never_red(fail_store):
    violations = _l26(fail_store)
    reported = {v.artifact for v in violations}
    assert "RU-0001" in reported and "RU-0002" in reported
    # the check that earned its green is not reported
    assert "RU-0003" not in reported


def test_l26_is_finding_class_never_a_red_build(fail_store):
    """A check may legitimately never have been observed red — it was written
    first, and the ledger only starts when recording starts. Blocking that
    would reward breaking a check once to record the red."""
    violations = _l26(fail_store)
    assert violations and all(v.severity == "finding" for v in violations)
    assert all("§6.8" in v.suggestion for v in violations)


def test_l26_says_how_to_settle_it(fail_store):
    violation = _l26(fail_store)[0]
    assert "never been observed failing" in violation.message
    assert "rqunit evidence record" in violation.suggestion


def test_l26_is_silent_on_a_store_with_no_ledger(tmp_path):
    root = _store(tmp_path, "fail")
    ledger_path(root).unlink()
    assert _l26(root) == []


# ------------------------------------------------------------ append-only

def test_the_guard_accepts_appends_and_rejects_a_rewrite(tmp_path):
    """The ledger legitimately grows on every recording, so the records'
    name-status rule would fire on honest use. What must hold is that the
    recorded history is still a PREFIX: evidence is added to, never edited —
    a first that can be deleted proves nothing."""
    import subprocess

    from click.testing import CliRunner

    from rqunit.cli.review import main as review_main

    root = _store(tmp_path, "fail")
    git = lambda *a: subprocess.run(["git", "-C", str(root), *a],
                                    check=True, capture_output=True)
    git("init", "-q")
    git("-c", "user.email=t@t", "-c", "user.name=t", "add", "-A")
    git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "base")

    def guard():
        return CliRunner().invoke(review_main, ["guard", "--store", str(root),
                                                "--against", "HEAD"])

    assert guard().exit_code == 0

    # appending a first is exactly what the command does — it must pass
    ledger = ledger_path(root)
    ledger.write_text(ledger.read_text() + json.dumps(
        {"at": "2026-03-01T00:00:00+00:00", "check_id": "svc::orders::records_reason",
         "observation": "first_red", "source": "run"}, sort_keys=True) + "\n")
    assert guard().exit_code == 0

    # deleting a recorded first is not
    kept = ledger.read_text().splitlines()[1:]
    ledger.write_text("\n".join(kept) + "\n")
    result = guard()
    assert result.exit_code == 1
    assert "no longer a prefix" in result.output
