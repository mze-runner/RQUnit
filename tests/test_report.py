"""`rqunit report` — the management snapshot. Invariants: the data contract
carries the documented sections; every number is derived (never asserted);
the HTML is fully self-contained (a report that fetches assets is useless in
an air-gapped review); store content is HTML-escaped; and the report is NOT a
committed projection (it carries a timestamp, which would break byte-currency)."""

import json
import re
import shutil
from pathlib import Path

import yaml
from click.testing import CliRunner

from rqunit.cli.report import main as report_main
from rqunit.generate import targets
from rqunit.report import build_data, render_html
from rqunit.store import Store

FIXTURES = Path(__file__).parent.parent / "fixtures"
VALID = FIXTURES / "store" / "valid"
NOW = "2026-07-29T09:00:00+00:00"


def _data(root=VALID) -> dict:
    return build_data(Store.load(root), Path(root), now=NOW)


def test_data_contract_shape():
    data = _data()
    assert set(data) >= {"contract_version", "generated_at", "store", "totals", "status",
                         "verification", "gates", "features", "areas", "burndown", "health"}
    assert data["status"]["active_total"] == len(
        [r for r in Store.load(VALID).rus() if r.status == "active"])
    assert set(data["totals"]) >= {"rus", "features", "contracts", "models", "adrs"}


def test_counts_are_derived_from_the_store_not_asserted(tmp_path):
    root = tmp_path / "store"
    shutil.copytree(VALID, root)
    before = build_data(Store.load(root), root, now=NOW)["totals"]["contracts"]
    (root / "spec" / "contracts" / "CT-extra.yaml").write_text(
        "id: CT-extra\nkind: claim-set\ndescription: Added to move the count.\n"
        "fields:\n- { name: sub, presence: always }\n")
    after = build_data(Store.load(root), root, now=NOW)["totals"]["contracts"]
    assert after == before + 1


def test_verification_completeness_tracks_todo_refs(tmp_path):
    root = tmp_path / "store"
    shutil.copytree(VALID, root)
    path = root / "spec" / "ru" / "RU-0002.yaml"
    raw = yaml.safe_load(path.read_text())
    raw["verification"].append({"type": "test", "ref": "TODO(not written yet)"})
    path.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True))
    data = build_data(Store.load(root), root, now=NOW)
    assert data["verification"]["todo_refs"].get("test", 0) >= 1
    feature = next(f for f in data["features"] if f["checks_total"])
    assert feature["checks_real"] <= feature["checks_total"]


def test_html_is_self_contained_and_deterministic():
    html = render_html(_data())
    assert html.startswith("<!DOCTYPE html>") and html.rstrip().endswith("</html>")
    # no network dependency: every src/href must be a fragment, never a URL
    external = [u for u in re.findall(r"""(?:src|href)=["'](?!#)([^"']+)""", html)]
    assert external == [], external
    assert "http://" not in html and "https://" not in html
    assert render_html(_data()) == html


def test_store_content_is_escaped(tmp_path):
    root = tmp_path / "store"
    shutil.copytree(VALID, root)
    # must be a feature with member RUs — empty features are not rendered
    feat = root / "spec" / "features" / "FEAT-order-cancellation.yaml"
    raw = yaml.safe_load(feat.read_text())
    raw["goal"] = 'Charges captured <script>alert("xss")</script> reliably.'
    feat.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True))
    html = render_html(build_data(Store.load(root), root, now=NOW))
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html


def test_report_explains_computed_status_semantics():
    # `done` is 0 until mechanical pass-states land; without the explanation a
    # reader would misread honest conservatism as catastrophe.
    html = render_html(_data())
    assert "computed" in html and "provably passes" in html
    assert "tracked" in html and "debt" in html


def test_report_is_not_a_committed_projection():
    generated = targets(Store.load(VALID), VALID)
    assert not any("report" in p.name for p in generated)


def test_cli_writes_html_and_json(tmp_path):
    runner = CliRunner()
    out = tmp_path / "r.html"
    result = runner.invoke(report_main, ["--store", str(VALID), "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert out.read_text().startswith("<!DOCTYPE html>")
    assert "active requirements" in result.output

    js = tmp_path / "r.json"
    result = runner.invoke(report_main, ["--store", str(VALID), "--out", str(js),
                                         "--format", "json"])
    assert result.exit_code == 0, result.output
    assert json.loads(js.read_text())["contract_version"] == 1
