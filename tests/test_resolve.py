"""`rqunit activate resolve` — Gate 1 TODO resolution (the debt-conversion
path). Invariants: TODO→resolved-ref conversion on an active RU lints clean
after the verb (no L19), stamped under the reviewer with the new ref
fingerprinted; the verb is strictly strengthening — real refs, missing
targets, wrong types, drafts, and ambiguous selections all refuse; hand
edits without the ceremony still red L19."""

import shutil
import textwrap
from pathlib import Path

import yaml
from click.testing import CliRunner

from rqunit.canonical import canonical_hash
from rqunit.cli.activate import main as activate_main
from rqunit.lints.base import run_lints
from rqunit.store import Store

FIXTURES = Path(__file__).parent.parent / "fixtures"
BASE = FIXTURES / "lints" / "L05" / "pass"   # RU-0003: resolved CT-base + one contract TODO


def _store(tmp_path: Path) -> Path:
    root = tmp_path / "store"
    shutil.copytree(BASE, root)
    (root / "spec" / "contracts" / "CT-extra.yaml").write_text(textwrap.dedent("""\
        id: CT-extra
        kind: claim-set
        description: Second contract, the resolution target.
        fields:
          - { name: sub, presence: always }
    """))
    return root


def _run(root: Path, *args):
    return CliRunner().invoke(
        activate_main, ["resolve", "--store", str(root), "--reviewer", "fixture-op", *args])


def _rule(root: Path, code: str):
    return [v for v in run_lints(Store.load(root), only=code) if v.rule == code]


def test_todo_converts_stamps_and_fingerprints_cleanly(tmp_path):
    root = _store(tmp_path)
    result = _run(root, "RU-0003=CT-extra")
    assert result.exit_code == 0, result.output
    assert "resolved RU-0003" in result.output and "CT-extra" in result.output

    assert not any(v.artifact == "RU-0003" for v in _rule(root, "L19"))
    assert _rule(root, "L5") == []
    ru = next(r for r in Store.load(root).rus() if r.id == "RU-0003")
    refs = [e["ref"] for e in ru.raw["verification"]]
    assert "CT-extra" in refs and not any(r.startswith("TODO(") for r in refs)
    assert "CT-base" in refs                                 # untouched sibling entry
    stamp = ru.raw["gate1_stamp"]
    assert stamp["by"] == "fixture-op" and stamp["hash"] == canonical_hash(ru.raw)
    fps = ru.raw["link_fingerprints"]
    assert fps["CT-extra"] == Store.load(root).contracts()["CT-extra"].content_hash


def test_ambiguous_same_type_todos_refuse_then_match_selects(tmp_path):
    root = _store(tmp_path)
    ru_path = root / "spec" / "ru" / "RU-0003.yaml"
    raw = yaml.safe_load(ru_path.read_text())
    raw["verification"].append({"type": "contract", "ref": "TODO(challenge claim-set check)"})
    ru_path.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True))

    refused = _run(root, "RU-0003=CT-extra")
    assert refused.exit_code != 0 and "ambiguous" in refused.output
    assert "claim-set check pending" in refused.output       # both candidates listed
    assert "challenge claim-set check" in refused.output

    selected = _run(root, "--match", "challenge", "RU-0003=CT-extra")
    assert selected.exit_code == 0, selected.output
    refs = [e["ref"] for e in yaml.safe_load(ru_path.read_text())["verification"]]
    assert "TODO(claim-set check pending)" in refs            # the other TODO survives


def test_strengthening_only_guards(tmp_path):
    root = _store(tmp_path)
    assert _run(root, "RU-0003=CT-ghost").exit_code != 0          # target must EXIST
    assert _run(root, "RU-0003=MDL-orders").exit_code != 0        # models excluded
    assert _run(root, "RU-9999=CT-extra").exit_code != 0          # unknown RU
    assert _run(root, "RU-0003:CT-extra").exit_code != 0          # malformed pair
    ok = _run(root, "RU-0003=CT-extra")
    assert ok.exit_code == 0
    again = _run(root, "RU-0003=CT-extra")                        # no TODOs left
    assert again.exit_code != 0 and "real refs are never replaced" in again.output
    email = CliRunner().invoke(activate_main, ["resolve", "--store", str(root),
                                               "--reviewer", "a@b.c", "RU-0003=CT-extra"])
    assert email.exit_code != 0


def test_test_type_targets_resolve_against_the_scan(tmp_path):
    root = _store(tmp_path)
    crate = root / "svc"
    (crate / "tests").mkdir(parents=True)
    (crate / "Cargo.toml").write_text('[package]\nname = "svc"\n')
    (crate / "tests" / "flow_tests.rs").write_text(
        "#[test]\nfn issues_token() {}\n")
    ru_path = root / "spec" / "ru" / "RU-0003.yaml"
    raw = yaml.safe_load(ru_path.read_text())
    raw["verification"].append({"type": "test", "ref": "TODO(issuance flow test)"})
    ru_path.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True))

    bogus = _run(root, "RU-0003=svc::flow_tests::no_such_fn")
    assert bogus.exit_code != 0 and "no scanned test" in bogus.output
    ok = _run(root, "RU-0003=svc::flow_tests::issues_token")
    assert ok.exit_code == 0, ok.output
    refs = [e["ref"] for e in yaml.safe_load(ru_path.read_text())["verification"]]
    assert "svc::flow_tests::issues_token" in refs
    assert "TODO(claim-set check pending)" in refs   # contract TODO untouched by a test target


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
            entry["ref"] = "CT-extra"
    ru_path.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True))
    assert any(v.artifact == "RU-0003" for v in _rule(root, "L19"))
