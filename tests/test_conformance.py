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


def _artifact(endpoints=None, messages=None, audit=None, service="service-orders") -> dict:
    """A whole-stack artifact: no `covers`, so it claims to have examined
    everything — which means it must report the audit events too, or its
    silence reads as 'the code records nothing' (CF10)."""
    return {
        "contract_version": 1,
        "generated_by": "test-adapter 0.0.0",
        "services": {service: {
            "endpoints": endpoints or [],
            "messages": messages or [],
            "audit_events": [{"code": c} for c in (audit if audit is not None
                                                   else ["orders.cancelled"])],
        }},
    }


def _ratify(entries):
    """Waivers live in the store, where Gate 1 governs them — never in the
    artifact, which an adapter writes."""
    return list(entries)


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
    artifact = _artifact(endpoints=[wrong], messages=[{"subject": "orders.cancelled"}])
    out = reconcile(store, artifact, exceptions=_ratify([{
        "rule": "CF4", "service": "service-orders",
        "target": "DELETE /api/v1/orders/{id}",
        "justification": "ingress enforces the tier, not route middleware",
    }]))
    assert len(out) == 1 and out[0].rule == "CF4"
    assert out[0].severity == "finding"                    # does not fail the run
    assert "RATIFIED EXCEPTION" in out[0].message          # but is still reported
    assert "ingress enforces" in out[0].message            # with its justification


def test_exception_matches_only_its_own_target(store):
    artifact = _artifact(
        endpoints=[{**DECLARED, "access": "public"}], messages=[{"subject": "orders.cancelled"}])
    out = reconcile(store, artifact, exceptions=_ratify([
        {"rule": "CF4", "service": "service-orders", "target": "GET /elsewhere",
         "justification": "a waiver for a different surface entirely"}]))
    assert out[0].severity == "error"


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

    # An artifact may no longer carry waivers at all — the migration message is
    # the whole point of rejecting it here rather than letting the schema say
    # only "additional properties are not allowed".
    with_waivers = tmp_path / "waiver.json"
    payload = _artifact()
    payload["exceptions"] = [{"rule": "CF4", "service": "s", "target": "GET /x",
                              "justification": "ingress enforces the tier, not middleware"}]
    with_waivers.write_text(json.dumps(payload))
    with pytest.raises(BadConfig) as caught:
        load_actual(with_waivers)
    assert "conformance-exceptions.yaml" in str(caught.value)


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


# ------------------------------------------------------- v0.13 shape matching

DECLARED_PATH = "/api/v1/orders/{id}"          # as the valid store's manifest spells it


def _endpoint(path=DECLARED_PATH, method="DELETE", access="protected", **shape):
    return {"method": method, "path": path, "access": access, **shape}


def test_placeholder_spelling_never_reads_as_two_divergences(store):
    """A framework that writes `:id` where the manifest writes `{id}` describes
    the same route. Matching raw strings would report CF1 and CF2 for every
    parameterized route in the store — two loud errors for nothing."""
    for spelling in ("/api/v1/orders/:id", "/api/v1/orders/<id>", "/api/v1/orders/{order_id}"):
        rules = _rules(reconcile(store, _artifact(endpoints=[_endpoint(path=spelling)])))
        assert "CF1" not in rules and "CF2" not in rules, spelling


def test_cf7_fires_in_both_directions_of_disagreement(store):
    artifact = _artifact(endpoints=[_endpoint(
        inbound={"type_name": "CancelParams", "fields": ["id", "tenant"]})])
    cf7 = [v for v in reconcile(store, artifact) if v.rule == "CF7"]
    messages = " ".join(v.message for v in cf7)
    assert "declares `inbound` field 'reason'" in messages     # manifest has it, code does not
    assert "carries `inbound` field 'tenant'" in messages      # code has it, manifest does not
    assert all(v.suggestion for v in cf7)


def test_cf7_is_silent_when_the_adapter_cannot_see_shapes(store):
    """Omission means 'not observed', never 'empty'. A stack whose extractor
    cannot resolve handlers must degrade to presence-only matching, not report
    every declared field as missing."""
    no_block = _artifact(endpoints=[_endpoint()])
    type_only = _artifact(endpoints=[_endpoint(inbound={"type_name": "CancelParams"})])
    for artifact in (no_block, type_only):
        assert "CF7" not in _rules(reconcile(store, artifact))


def test_cf8_uses_the_code_type_as_the_shape_identity(store, tmp_path):
    """Censuses are declared per surface with no shared id. The code's type is
    what says two of them describe the same thing."""
    shutil.copytree(VALID, tmp_path / "s")
    manifest = tmp_path / "s" / "spec" / "manifests" / "service-orders.manifest.yaml"
    raw = yaml.safe_load(manifest.read_text())
    original = raw["endpoints"][0]
    twin = dict(original)
    twin["id"] = "cancel_order_v2"
    twin["path"] = "/api/v2/orders/{id}"
    twin["outbound"] = {"status": 200, "fields": [{"name": "order_id", "presence": "always"}]}
    original["outbound"] = {"status": 200,
                            "fields": [{"name": "order_id", "presence": "always"},
                                       {"name": "cancelled_at", "presence": "always"}]}
    raw["endpoints"] = [original, twin]
    manifest.write_text(yaml.safe_dump(raw, sort_keys=False))

    served = {"type_name": "CancelView", "fields": ["order_id", "cancelled_at"]}
    artifact = _artifact(endpoints=[
        _endpoint(outbound=served),
        _endpoint(path="/api/v2/orders/{id}", outbound=served)])
    cf8 = [v for v in reconcile(Store.load(tmp_path / "s"), artifact) if v.rule == "CF8"]
    assert cf8 and "CancelView" in cf8[0].message and "cancelled_at" in cf8[0].message


def test_cf8_groups_nothing_when_the_shape_has_no_name(store, tmp_path):
    """The other side of the same rule, and the half a whole stack depended on.
    CF8's premise is that the code's TYPE is the shared identity; a return type
    that carries no shape has no identity to share. An adapter reporting an
    erased wrapper (axum's `Response`) as a type name made every pair of
    endpoints in a service look like it served one type and disagreed about it —
    so core must group on a name it was given, never on its absence."""
    shutil.copytree(VALID, tmp_path / "s")
    manifest = tmp_path / "s" / "spec" / "manifests" / "service-orders.manifest.yaml"
    raw = yaml.safe_load(manifest.read_text())
    original = raw["endpoints"][0]
    twin = dict(original)
    twin["id"] = "cancel_order_v2"
    twin["path"] = "/api/v2/orders/{id}"
    twin["outbound"] = {"status": 200, "fields": [{"name": "order_id", "presence": "always"}]}
    original["outbound"] = {"status": 200,
                            "fields": [{"name": "order_id", "presence": "always"},
                                       {"name": "cancelled_at", "presence": "always"}]}
    raw["endpoints"] = [original, twin]
    manifest.write_text(yaml.safe_dump(raw, sort_keys=False))

    # Two surfaces, different declared censuses, and an extractor that reports no
    # type name for either — which is what "this return type carries no shape"
    # looks like on the wire.
    artifact = _artifact(endpoints=[
        _endpoint(outbound={"fields": ["order_id"]}),
        _endpoint(path="/api/v2/orders/{id}", outbound={"fields": ["order_id"]})])

    assert "CF8" not in _rules(reconcile(Store.load(tmp_path / "s"), artifact))


def test_shape_divergence_is_ratifiable_like_any_other(store):
    """A serializer that suppresses a field at runtime is a real, defensible
    difference — but it has to be written down and stays reported."""
    artifact = _artifact(
        endpoints=[_endpoint(inbound={"type_name": "CancelParams", "fields": ["id"]})])
    cf7 = [v for v in reconcile(store, artifact, exceptions=_ratify([
        {"rule": "CF7", "service": "service-orders", "target": f"DELETE {DECLARED_PATH}",
         "justification": "reason is populated by middleware, not by the request type"}]))
        if v.rule == "CF7"]
    assert cf7 and all(v.severity == "finding" for v in cf7)
    assert "RATIFIED EXCEPTION" in cf7[0].message


def test_provenance_counts_what_extraction_did_not_reach(store):
    from rqunit.conformance import boundary_provenance

    blind = boundary_provenance(store, [_artifact(endpoints=[_endpoint()])])
    seeing = boundary_provenance(store, [_artifact(endpoints=[_endpoint(
        inbound={"type_name": "CancelParams", "fields": ["id", "reason"]})])])
    assert blind["fields_extractor_confirmed"] == 0
    assert seeing["fields_extractor_confirmed"] > blind["fields_extractor_confirmed"]
    assert seeing["fields_unproven_by_extraction"] < blind["fields_unproven_by_extraction"]
    # An unproven field is not a failure — it is the part of the boundary that
    # carries target state, and the point is that it stays countable.
    assert seeing["shapes_declared"] >= 1


# ------------------------------------------------- probe coverage (covers/merge)

def _probe(covers, service="service-orders", **surface):
    return {"contract_version": 1, "generated_by": f"{covers[0]}-probe 0.1",
            "covers": list(covers), "services": {service: surface}}


def test_a_probe_is_not_read_as_denying_what_it_never_examined(store):
    """The whole reason `covers` exists: a NATS probe says nothing about routes,
    and silence must not be read as 'the code serves none'."""
    from rqunit.conformance import merge

    nats_only = _probe(["messages"], messages=[{"subject": "orders.cancelled"}])
    assert "CF1" not in _rules(reconcile(store, merge([nats_only])))
    # ...whereas a whole-stack artifact (no `covers`) still means "I saw it all",
    # so its silence about endpoints stays a real divergence.
    legacy = {"contract_version": 1, "generated_by": "whole-stack 0.1",
              "services": {"service-orders": {"messages": [{"subject": "orders.cancelled"}]}}}
    assert "CF1" in _rules(reconcile(store, merge([legacy])))


def test_two_probes_do_not_report_each_other(store):
    """Assembly before judgment. Judged separately, the HTTP probe calls the
    NATS subject undeclared and the NATS probe calls the route unserved — two
    correct probes, and the service red twice for nothing."""
    from rqunit.conformance import merge

    http = _probe(["endpoints"], endpoints=[
        {"method": "DELETE", "path": "/api/v1/orders/:id", "access": "protected"}])
    nats = _probe(["messages"], messages=[{"subject": "orders.cancelled"}])
    assert reconcile(store, merge([http, nats])) == []


def test_cf9_fires_when_a_declared_family_went_unexamined(store):
    """`covers` alone would trade false errors for silence, which is worse: the
    run goes green because nobody asked. CF9 is the other half."""
    from rqunit.conformance import merge, uncovered_families

    http_only = _probe(["endpoints"], endpoints=[
        {"method": "DELETE", "path": "/api/v1/orders/:id", "access": "protected"}])
    merged = merge([http_only])
    cf9 = uncovered_families(store, merged)
    families = {v.artifact.split(":")[1] for v in cf9}
    assert "messages" in families and "channels" in families
    assert all(v.severity == "error" and v.suggestion for v in cf9)
    assert "never examined" in cf9[0].message


def test_cf9_leaves_services_no_adapter_covers_alone(store):
    """A service outside every adapter's reach is deliberately out of scope —
    the artifact contract has said so since it was written. CF9 is the narrower
    claim that a COVERED service has an unlooked-at family."""
    from rqunit.conformance import merge, uncovered_families

    merged = merge([_probe(["endpoints", "messages", "channels"], endpoints=[])])
    assert not [v for v in uncovered_families(store, merged) if "service-billing" in v.artifact]


# ------------------------------------------------- waivers live in the store

def _store_with_exceptions(tmp_path, body: str) -> Path:
    root = tmp_path / "s"
    shutil.copytree(VALID, root)
    (root / "spec" / "framework" / "conformance-exceptions.yaml").write_text(body)
    return root


def test_a_waiver_in_the_store_downgrades_the_finding(tmp_path):
    from rqunit.conformance import load_exceptions

    root = _store_with_exceptions(tmp_path, """
exceptions:
  - rule: CF4
    service: service-orders
    target: "DELETE /api/v1/orders/{id}"
    justification: ingress enforces the tier, not route middleware
""")
    store = Store.load(root)
    assert len(load_exceptions(root)) == 1
    artifact = _artifact(endpoints=[{**DECLARED, "access": "public"}],
                         messages=[{"subject": "orders.cancelled"}])
    out = reconcile(store, artifact)                       # loads waivers from the store itself
    assert out[0].rule == "CF4" and out[0].severity == "finding"
    assert "RATIFIED EXCEPTION" in out[0].message


def test_an_indefensible_waiver_is_a_configuration_error(tmp_path):
    """The rule that matters is not structural: a one-word waiver passes any
    shape check and defends nothing."""
    from rqunit.conformance import load_exceptions

    root = _store_with_exceptions(tmp_path, """
exceptions:
  - rule: CF4
    service: service-orders
    target: "DELETE /api/v1/orders/{id}"
    justification: legacy
""")
    with pytest.raises(BadConfig) as caught:
        load_exceptions(root)
    assert "wearing a waiver" in str(caught.value)


def test_a_store_with_no_waiver_file_simply_has_none(tmp_path):
    from rqunit.conformance import load_exceptions

    assert load_exceptions(VALID) == []


def test_the_report_says_how_much_of_the_boundary_extraction_reached(tmp_path):
    """A manifest may exceed what an extractor can see — that is how it carries
    target state. The cost is that a green run says nothing about the part
    nobody reached, so the unproven fraction must be in the report."""
    artifact = tmp_path / "a.json"
    artifact.write_text(json.dumps({
        "contract_version": 1, "generated_by": "probe 0.1",
        "covers": ["endpoints", "messages", "channels", "audit_events"],
        "services": {"service-orders": {"endpoints": [
            {"method": "DELETE", "path": "/api/v1/orders/:id", "access": "protected",
             "inbound": {"type_name": "CancelParams", "fields": ["id", "reason"]}}],
            "messages": [{"subject": "orders.cancelled", "direction": "outbound"}],
            "audit_events": [{"code": "orders.cancelled"}]}}}))
    runner = CliRunner()
    out = runner.invoke(conformance_main, ["--store", str(VALID), "--artifact", str(artifact)])
    assert out.exit_code == 0, out.output
    boundary = json.loads(out.output)["boundary"]
    assert boundary["fields_extractor_confirmed"] > 0
    assert boundary["fields_unproven_by_extraction"] > 0    # and it is visible, not implied

    text = runner.invoke(conformance_main, ["--store", str(VALID), "--artifact", str(artifact),
                                            "--format", "text"])
    assert "extractor-confirmed" in text.output


# ------------------------------------------------- audit conformance (CF10/11)

def _audit_artifact(codes, service="service-orders"):
    return {"contract_version": 1, "generated_by": "audit-probe 0.1",
            "covers": ["audit_events"],
            "services": {service: {"audit_events": [{"code": c} for c in codes]}}}


def test_cf10_catches_the_audit_event_nobody_records(store):
    """Until v0.14 a service could declare twenty audit events, emit none, and
    pass every gate: `emits` was checked for resolvability, never for existence
    in code."""
    from rqunit.conformance import merge

    out = reconcile(store, merge([_audit_artifact([])]))
    cf10 = [v for v in out if v.rule == "CF10"]
    assert cf10 and "never recorded by the code" in cf10[0].message
    assert "RU-0002" in cf10[0].suggestion          # names the constitutional requirement


def test_cf11_catches_evidence_nobody_declared(store):
    """An undeclared audit record has no retention rule and no forbidden-field
    check — the two things that make it evidence rather than a log line."""
    from rqunit.conformance import merge

    out = reconcile(store, merge([_audit_artifact(["orders.cancelled", "orders.ghost"])]))
    cf11 = [v for v in out if v.rule == "CF11"]
    assert cf11 and "orders.ghost" in cf11[0].message
    assert not [v for v in out if v.rule == "CF10"]  # the declared one WAS recorded


def test_audit_reconciliation_respects_coverage(store):
    """A probe that never looked at audit must not have its silence read as
    'the code records nothing' — the same rule that protects every family."""
    from rqunit.conformance import merge

    http_only = {"contract_version": 1, "generated_by": "http-probe 0.1",
                 "covers": ["endpoints"], "services": {"service-orders": {"endpoints": []}}}
    assert "CF10" not in _rules(reconcile(store, merge([http_only])))


def test_an_unexamined_audit_family_is_reported(store):
    """`covers` alone would trade a false error for silence. CF9 is the half
    that keeps the unasked question visible."""
    from rqunit.conformance import merge, uncovered_families

    merged = merge([{"contract_version": 1, "generated_by": "http 0.1",
                     "covers": ["endpoints", "messages", "channels"],
                     "services": {"service-orders": {"endpoints": []}}}])
    families = {v.artifact.split(":")[1] for v in uncovered_families(store, merged)}
    assert "audit_events" in families


def test_cf7_reads_negative_presence_the_right_way_round(store):
    """A `never`/`forbidden` field is declared precisely so it is NOT there.
    Reporting its absence inverts the claim — and checking only for absence
    misses the case that matters: the field appearing anyway."""
    from rqunit.conformance import merge

    # the valid store's cancel_order inbound declares `reason` (required)
    absent_negative = _artifact(endpoints=[_endpoint(
        inbound={"type_name": "CancelParams", "fields": ["id", "reason"]})])
    assert "CF7" not in _rules(reconcile(store, merge([absent_negative])))

    # now the code carries something the census forbids
    leaking = _artifact(endpoints=[_endpoint(
        inbound={"type_name": "CancelParams", "fields": ["id", "reason", "password"]})])
    cf7 = [v for v in reconcile(store, merge([leaking])) if v.rule == "CF7"]
    assert cf7 and "does not declare" in cf7[0].message
