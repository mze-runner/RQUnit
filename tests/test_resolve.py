"""`rqunit activate resolve` — Gate 1 TODO resolution (the debt-conversion path).

Invariants: TODO→resolved-ref conversion on an active RU lints clean after the
verb (no L19), stamped under the reviewer; the verb is strictly strengthening —
real refs, missing targets, drafts, and ambiguous selections all refuse; hand
edits without the ceremony still red L19.

v0.14: the only resolvable target is a scanned test id. Contract refs were the
other half until shapes became manifest facts, which left `resolve` with one
type and no type-matching to do.
"""

import shutil
from pathlib import Path

import yaml
from click.testing import CliRunner

from rqunit.canonical import canonical_hash
from rqunit.cli.activate import main as activate_main
from rqunit.lints.base import run_lints
from rqunit.store import Store

FIXTURES = Path(__file__).parent.parent / "fixtures"
BASE = FIXTURES / "lints" / "L05" / "pass"      # RU-0003 carries two test TODOs


def _store(tmp_path: Path) -> Path:
    """A store with a scannable companion crate — resolution needs a real test
    to point at, because a TODO converts only to a check that EXISTS."""
    root = tmp_path / "store"
    shutil.copytree(BASE, root)
    (root / "rqunit.toml").write_text(
        '[stacks.rust.adapter]\nscanner = { artifact = "scanned-checks.json" }\n')
    crate = root / "svc"
    (crate / "tests").mkdir(parents=True)
    (crate / "Cargo.toml").write_text('[package]\nname = "svc"\n')
    (crate / "tests" / "flow_tests.rs").write_text(
        "#[test]\nfn issues_token() {}\n\n#[test]\nfn records_decision() {}\n")
    import json
    (root / "scanned-checks.json").write_text(json.dumps({
        "contract_version": 1, "generated_by": "fixture-scanner 0.1",
        "checks": [
            {"id": "svc::flow_tests::issues_token", "path": "svc/tests/flow_tests.rs",
             "fn": "issues_token", "verifies": []},
            {"id": "svc::flow_tests::records_decision", "path": "svc/tests/flow_tests.rs",
             "fn": "records_decision", "verifies": []},
        ]}))
    return root


def _run(root: Path, *args):
    return CliRunner().invoke(
        activate_main, ["resolve", "--store", str(root), "--reviewer", "fixture-op", *args])


def _rule(root: Path, code: str):
    return [v for v in run_lints(Store.load(root), only=code) if v.rule == code]


def _refs(root: Path, ru_id="RU-0003"):
    raw = yaml.safe_load((root / "spec" / "ru" / f"{ru_id}.yaml").read_text())
    return [e["ref"] for e in raw["verification"]]


def test_todo_converts_stamps_cleanly(tmp_path):
    root = _store(tmp_path)
    result = _run(root, "--match", "base", "RU-0003=svc::flow_tests::issues_token")
    assert result.exit_code == 0, result.output
    assert "resolved RU-0003" in result.output

    assert not any(v.artifact == "RU-0003" for v in _rule(root, "L19"))
    assert _rule(root, "L5") == []
    ru = next(r for r in Store.load(root).rus() if r.id == "RU-0003")
    refs = [e["ref"] for e in ru.raw["verification"]]
    assert "svc::flow_tests::issues_token" in refs
    assert any(r.startswith("TODO(") for r in refs)        # the sibling TODO survives
    stamp = ru.raw["gate1_stamp"]
    assert stamp["by"] == "fixture-op" and stamp["hash"] == canonical_hash(ru.raw)


def test_ambiguous_todos_refuse_then_match_selects(tmp_path):
    root = _store(tmp_path)
    refused = _run(root, "RU-0003=svc::flow_tests::issues_token")
    assert refused.exit_code != 0 and "ambiguous" in refused.output
    assert "base census" in refused.output                 # both candidates listed
    assert "claim_set check" in refused.output

    selected = _run(root, "--match", "claim_set", "RU-0003=svc::flow_tests::issues_token")
    assert selected.exit_code == 0, selected.output
    refs = _refs(root)
    assert "svc::flow_tests::issues_token" in refs
    assert any("base census" in r for r in refs)           # the unselected TODO survives


def test_strengthening_only_guards(tmp_path):
    root = _store(tmp_path)
    assert _run(root, "RU-0003=svc::flow_tests::no_such_fn").exit_code != 0   # must EXIST
    assert _run(root, "RU-0003=MDL-orders").exit_code != 0                    # models excluded
    assert _run(root, "RU-9999=svc::flow_tests::issues_token").exit_code != 0  # unknown RU
    assert _run(root, "RU-0003:svc::flow_tests::issues_token").exit_code != 0  # malformed pair

    assert _run(root, "--match", "base", "RU-0003=svc::flow_tests::issues_token").exit_code == 0
    assert _run(root, "--match", "claim_set",
                "RU-0003=svc::flow_tests::records_decision").exit_code == 0
    again = _run(root, "RU-0003=svc::flow_tests::issues_token")               # no TODOs left
    assert again.exit_code != 0 and "real refs are never replaced" in again.output

    email = CliRunner().invoke(activate_main, ["resolve", "--store", str(root),
                                               "--reviewer", "a@b.c",
                                               "RU-0003=svc::flow_tests::issues_token"])
    assert email.exit_code != 0


def test_hand_editing_without_the_ceremony_still_reds_l19(tmp_path):
    root = _store(tmp_path)
    ru_path = root / "spec" / "ru" / "RU-0003.yaml"
    raw = yaml.safe_load(ru_path.read_text())
    raw["gate1_stamp"] = {"hash": canonical_hash(raw), "by": "fixture-op",
                          "at": "2026-07-28T10:00:00+00:00"}
    ru_path.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True))
    assert not any(v.artifact == "RU-0003" for v in _rule(root, "L19"))

    for entry in raw["verification"]:
        if entry["ref"].startswith("TODO("):
            entry["ref"] = "svc::flow_tests::issues_token"
    ru_path.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True))
    assert any(v.artifact == "RU-0003" for v in _rule(root, "L19"))
