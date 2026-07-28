"""Manifest ↔ code conformance (spec §5.6/§5.8) — the diff core owns.

Invariants: every divergence class fires on its own defect; the planned
asymmetry holds in BOTH directions (absent is expected, present is CF3);
ratified exceptions downgrade to a reported finding and never silence;
malformed artifacts are configuration errors, not conformance verdicts; and
the reconciler judges from the STORE, never from a language."""

import json
import shutil
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from rqunit.cli.conformance import main as conformance_main
from rqunit.conformance import load_actual, reconcile
from rqunit.errors import BadConfig
from rqunit.store import Store

FIXTURES = Path(__file__).parent.parent / "fixtures"
VALID = FIXTURES / "store" / "valid"


def _artifact(endpoints=None, messages=None, exceptions=None, service="service-orders") -> dict:
    return {
        "contract_version": 1,
        "generated_by": "test-adapter 0.0.0",
        "services": {service: {"endpoints": endpoints or [], "messages": messages or []}},
        "exceptions": exceptions or [],
    }


def _rules(violations) -> list[str]:
    return [v.rule for v in violations]


@pytest.fixture()
def store() -> Store:
    return Store.load(VALID)


# the valid fixture declares DELETE /api/v1/orders/{id} (protected) and
# outbound 'orders.cancelled'
DECLARED = {"method": "DELETE", "path": "/api/v1/orders/{id}", "access": "protected"}


def test_matching_surface_is_clean(store):
    out = reconcile(store, _artifact(
        endpoints=[DECLARED], messages=[{"subject": "orders.cancelled"}]))
    assert out == []


def test_cf1_declared_but_not_served(store):
    out = reconcile(store, _artifact(messages=[{"subject": "orders.cancelled"}]))
    assert "CF1" in _rules(out)
    assert any("not served" in v.message for v in out)


def test_cf2_served_but_undeclared(store):
    extra = {"method": "GET", "path": "/api/v1/orders/secret", "access": "public"}
    out = reconcile(store, _artifact(
        endpoints=[DECLARED, extra], messages=[{"subject": "orders.cancelled"}]))
    assert "CF2" in _rules(out)
    assert any("no manifest declares it" in v.message for v in out)


def test_cf4_access_tier_mismatch(store):
    wrong = {**DECLARED, "access": "public"}
    out = reconcile(store, _artifact(
        endpoints=[wrong], messages=[{"subject": "orders.cancelled"}]))
    assert _rules(out) == ["CF4"]
    assert "manifest 'protected', code 'public'" in out[0].message


def test_cf6_publishes_undeclared_subject(store):
    out = reconcile(store, _artifact(
        endpoints=[DECLARED],
        messages=[{"subject": "orders.cancelled"}, {"subject": "orders.ghost"}]))
    assert "CF6" in _rules(out)


def test_planned_asymmetry_holds_both_ways(tmp_path):
    """Absent-and-planned is expected; served-and-planned is CF3 (§5.8)."""
    root = tmp_path / "store"
    shutil.copytree(VALID, root)
    path = root / "spec" / "manifests" / "service-orders.manifest.yaml"
    raw = yaml.safe_load(path.read_text())
    raw["endpoints"][0]["planned"] = True
    path.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True))
    store = Store.load(root)

    absent = reconcile(store, _artifact(messages=[{"subject": "orders.cancelled"}]))
    assert "CF1" not in _rules(absent)          # planned + absent: expected

    served = reconcile(store, _artifact(
        endpoints=[DECLARED], messages=[{"subject": "orders.cancelled"}]))
    assert _rules(served) == ["CF3"]            # planned + served: its own class
    assert "still marks it planned" in served[0].message


def test_exceptions_downgrade_but_never_silence(store):
    wrong = {**DECLARED, "access": "public"}
    artifact = _artifact(endpoints=[wrong], messages=[{"subject": "orders.cancelled"}],
                         exceptions=[{
                             "rule": "CF4", "service": "service-orders",
                             "target": "DELETE /api/v1/orders/{id}",
                             "justification": "ingress enforces the tier, not route middleware",
                         }])
    out = reconcile(store, artifact)
    assert len(out) == 1 and out[0].rule == "CF4"
    assert out[0].severity == "finding"                    # does not fail the run
    assert "RATIFIED EXCEPTION" in out[0].message          # but is still reported
    assert "ingress enforces" in out[0].message            # with its justification


def test_exception_matches_only_its_own_target(store):
    artifact = _artifact(
        endpoints=[{**DECLARED, "access": "public"}], messages=[{"subject": "orders.cancelled"}],
        exceptions=[{"rule": "CF4", "service": "service-orders", "target": "GET /elsewhere",
                     "justification": "a waiver for a different surface entirely"}])
    assert reconcile(store, artifact)[0].severity == "error"


def test_service_without_a_manifest_is_an_error(store):
    out = reconcile(store, _artifact(service="service-ghost"))
    assert out and "no manifest" in out[0].message


# ------------------------------------------------------------ artifact contract

def test_malformed_artifacts_are_config_errors(tmp_path):
    missing = tmp_path / "nope.json"
    with pytest.raises(BadConfig):
        load_actual(missing)

    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{not json")
    with pytest.raises(BadConfig):
        load_actual(bad_json)

    off_contract = tmp_path / "off.json"
    off_contract.write_text(json.dumps({"contract_version": 1, "services": {}}))  # no generated_by
    with pytest.raises(BadConfig):
        load_actual(off_contract)

    unjustified = tmp_path / "waiver.json"
    unjustified.write_text(json.dumps(_artifact(exceptions=[{
        "rule": "CF4", "service": "s", "target": "GET /x", "justification": "because"}])))
    with pytest.raises(BadConfig):        # justification has a minimum length by design
        load_actual(unjustified)


def test_cli_exit_codes(tmp_path):
    runner = CliRunner()
    artifact = tmp_path / "a.json"
    artifact.write_text(json.dumps(_artifact(
        endpoints=[DECLARED], messages=[{"subject": "orders.cancelled"}])))
    ok = runner.invoke(conformance_main, ["--store", str(VALID), "--artifact", str(artifact)])
    assert ok.exit_code == 0, ok.output

    artifact.write_text(json.dumps(_artifact(messages=[{"subject": "orders.cancelled"}])))
    red = runner.invoke(conformance_main, ["--store", str(VALID), "--artifact", str(artifact),
                                           "--format", "text"])
    assert red.exit_code == 1 and "CF1" in red.output
