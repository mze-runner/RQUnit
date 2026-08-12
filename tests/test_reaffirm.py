"""GAP22 — model evolution's lawful path. Invariants: a model edit reds the
store (L6, actives/drafts only); `spec-activate reaffirm` clears it by
re-stamping active dependents under the reviewer's id; superseded RUs keep
their historical hashes untouched (provenance, never currency); hand-editing
without the verb still reds L19."""

import json
import shutil
from pathlib import Path

import yaml
from click.testing import CliRunner

from rqunit.canonical import canonical_hash
from rqunit.cli.activate import main as activate_main
from rqunit.lints.base import run_lints
from rqunit.store import Store

FIXTURES = Path(__file__).parent.parent / "fixtures"
VALID = FIXTURES / "store" / "valid"


def _store_with_edited_model(tmp_path: Path) -> Path:
    root = tmp_path / "store"
    shutil.copytree(VALID, root)
    model_path = root / "spec" / "models" / "MDL-order-lifecycle.statechart.json"
    model = json.loads(model_path.read_text())
    next(iter(model["states"].values()))["invariant"] = "reaffirm_probe"
    model_path.write_text(json.dumps(model, indent=2) + "\n")
    # The fixture's artifact-mode emit response cannot re-render an edited
    # model (that staleness failing loudly is its own tested behavior); this
    # test is about hash ceremony, so the store declares no emitter and the
    # verbs' projection refresh runs the lenient path.
    (root / "rqunit.toml").write_text("[stacks.rust]\n")
    return root


def _rule(root: Path, code: str):
    return [v for v in run_lints(Store.load(root), only=code) if v.rule == code]


def test_model_edit_reds_actives_then_reaffirm_clears_it(tmp_path):
    root = _store_with_edited_model(tmp_path)
    assert _rule(root, "L6"), "editing the model must red its active dependents"

    result = CliRunner().invoke(activate_main, [
        "reaffirm", "--model", "order-lifecycle",
        "--reviewer", "fixture-op", "--store", str(root)])
    assert result.exit_code == 0, result.output

    assert _rule(root, "L6") == []
    assert _rule(root, "L19") == []
    ru = next(r for r in Store.load(root).rus() if r.id == "RU-0142")
    stamp = ru.raw["gate1_stamp"]
    assert stamp["by"] == "fixture-op"
    assert stamp["hash"] == canonical_hash(ru.raw)
    model = Store.load(root).models()["order-lifecycle"]
    assert all(e["model_hash"] == model.content_hash
               for e in ru.raw["verification"] if e.get("type") == "model")


def test_superseded_hashes_are_provenance_not_currency(tmp_path):
    root = _store_with_edited_model(tmp_path)
    ru_dir = root / "spec" / "ru"
    historical = yaml.safe_load((ru_dir / "RU-0142.yaml").read_text())
    historical.update(id="RU-0140", status="superseded")
    (ru_dir / "RU-0140.yaml").write_text(
        yaml.safe_dump(historical, sort_keys=False, allow_unicode=True))
    old_hash = next(e["model_hash"] for e in historical["verification"]
                    if e.get("type") == "model")

    assert all(v.artifact != "RU-0140" for v in _rule(root, "L6"))
    result = CliRunner().invoke(activate_main, [
        "reaffirm", "--model", "MDL-order-lifecycle",
        "--reviewer", "fixture-op", "--store", str(root)])
    assert result.exit_code == 0, result.output
    after = yaml.safe_load((ru_dir / "RU-0140.yaml").read_text())
    assert next(e["model_hash"] for e in after["verification"]
                if e.get("type") == "model") == old_hash


def test_reaffirm_refuses_contact_info_and_unknown_targets(tmp_path):
    root = _store_with_edited_model(tmp_path)
    runner = CliRunner()
    assert runner.invoke(activate_main, [
        "reaffirm", "--model", "order-lifecycle",
        "--reviewer", "a@b.c", "--store", str(root)]).exit_code != 0
    assert runner.invoke(activate_main, [
        "reaffirm", "--model", "no-such-model",
        "--reviewer", "fixture-op", "--store", str(root)]).exit_code != 0
    assert runner.invoke(activate_main, [
        "reaffirm", "--model", "order-lifecycle", "--ru", "RU-9999",
        "--reviewer", "fixture-op", "--store", str(root)]).exit_code != 0


def test_reaffirm_is_a_noop_on_a_current_store(tmp_path):
    root = tmp_path / "store"
    shutil.copytree(VALID, root)
    before = {p: p.read_text() for p in (root / "spec" / "ru").glob("*.yaml")}
    result = CliRunner().invoke(activate_main, [
        "reaffirm", "--model", "order-lifecycle",
        "--reviewer", "fixture-op", "--store", str(root)])
    assert result.exit_code == 0 and "nothing to re-affirm" in result.output
    assert {p: p.read_text() for p in (root / "spec" / "ru").glob("*.yaml")} == before


def test_hand_editing_the_hash_without_the_verb_still_reds_l19(tmp_path):
    root = _store_with_edited_model(tmp_path)
    path = root / "spec" / "ru" / "RU-0142.yaml"
    raw = yaml.safe_load(path.read_text())
    model = Store.load(root).models()["order-lifecycle"]
    for entry in raw["verification"]:
        if entry.get("type") == "model":
            entry["model_hash"] = model.content_hash
    path.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True))
    assert any(v.artifact == "RU-0142" for v in _rule(root, "L19"))


def test_reaffirm_refuses_a_model_that_cannot_render_before_writing(tmp_path):
    """This verb runs immediately after a model edit — exactly when a dialect
    violation is most likely. It used to re-stamp every affected RU and THEN
    die inside regeneration, leaving RUs stamped against a model that never
    generated."""
    root = _store_with_edited_model(tmp_path)
    model_path = root / "spec" / "models" / "MDL-order-lifecycle.statechart.json"
    model = json.loads(model_path.read_text())
    first = next(iter(model["states"]))
    model["states"][first]["on"] = {"GHOST": "nowhere"}       # M2
    model_path.write_text(json.dumps(model, indent=2) + "\n")

    before = {p: p.read_text() for p in (root / "spec" / "ru").glob("*.yaml")}
    result = CliRunner().invoke(activate_main, [
        "reaffirm", "--model", "order-lifecycle",
        "--reviewer", "fixture-op", "--store", str(root)])

    assert result.exit_code == 1
    assert "nothing was written" in result.output and "[M2]" in result.output
    assert {p: p.read_text() for p in (root / "spec" / "ru").glob("*.yaml")} == before
