# RU Framework — reference-pack smoke tests, installed per TASK-002.
# Adaptation from the shipped smoke_tests.py is limited to the loading block:
# schemas load from spec/framework/ (the committed normative copies) and the
# feat-and-gap pack file is split into feat.schema.yaml + gap.schema.yaml.
# Every test case is byte-identical to the reference pack. TASK-002 fixture
# suites EXTEND these cases (tests/test_schema_fixtures.py), never replace them.

import copy

import pytest
import yaml
from jsonschema import Draft202012Validator, ValidationError, validate

from rqunit.schemas import load_schema

RU = load_schema("ru")
MANIFEST = load_schema("manifest")
MODEL = load_schema("model")
FG = {"feat": load_schema("feat"), "gap": load_schema("gap")}

def ok(instance, schema):
    validate(instance, schema, cls=Draft202012Validator)

def bad(instance, schema):
    with pytest.raises(ValidationError):
        validate(instance, schema, cls=Draft202012Validator)

# ---------------------------------------------------------------- meta
@pytest.mark.parametrize("schema", [RU, MANIFEST, MODEL, FG["feat"], FG["gap"]])
def test_schema_is_valid_jsonschema_2020_12(schema):
    Draft202012Validator.check_schema(schema)

def test_no_yaml_boolean_keys_anywhere():
    """YAML-1.1 parses unquoted on/off/yes/no as booleans; a boolean key in a
    schema silently changes its meaning. This caught a real bug once."""
    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                assert not isinstance(k, bool), f"boolean key {k!r} — quote it in the YAML source"
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    for s in (RU, MANIFEST, MODEL, FG):
        walk(s)

# ---------------------------------------------------------------- RU
RU_BASE = yaml.safe_load("""
id: RU-0142
statement: >
  When a customer-support-agent calls {endpoint:cancel_order}, the system
  shall halt fulfilment activity for that order_id within 5 seconds.
syntax: ears
status: active
feature: FEAT-order-cancellation
source_ref: INT-0057#L34-41
rationale_ref: ADR-0031
verification:
  - type: model
    ref: MDL-order-lifecycle
    model_hash: "sha256:9f1c00000000000000000000000000000000000000000000000000000000abcd"
    conformance: generated
  - type: test
    ref: itest::orders::cancellation_latency_bound
scope:
  owns: [orders/fulfilment]
  must_not_touch: [payments/capture]
tags: [orders, cancellation]
""")

def test_ru_worked_example_validates():
    ok(RU_BASE, RU)

def test_ru_forbidden_field_priority_rejected():          # spec §3.2 / L8 backstop
    r = copy.deepcopy(RU_BASE); r["priority"] = 1
    bad(r, RU)

def test_ru_draft_status_with_permanent_id_rejected():    # spec §3.1
    r = copy.deepcopy(RU_BASE); r["status"] = "draft"
    bad(r, RU)

def test_ru_manual_conformance_without_justification_rejected():   # spec §6.3
    r = copy.deepcopy(RU_BASE); r["verification"][0]["conformance"] = "manual"
    bad(r, RU)

def test_ru_manual_conformance_with_justification_ok():
    r = copy.deepcopy(RU_BASE)
    r["verification"][0]["conformance"] = "manual"
    r["verification"][0]["justification"] = "Legacy suite predates generator; migration tracked."
    ok(r, RU)

def test_ru_todo_ref_ok():                                # spec §6.5
    r = copy.deepcopy(RU_BASE)
    r["verification"].append({"type": "contract", "ref": "TODO(CT: prices pinned at confirmation)"})
    ok(r, RU)

CONST_RU = yaml.safe_load("""
id: RU-0002
statement: The system shall record an audit event for every state-changing action.
syntax: ears
status: active
tier: constitutional
source_ref: INT-0001#L10-12
verification:
  - { type: contract, ref: CT-audit-on-mutation }
tags: [doctrine, audit]
""")

def test_ru_constitutional_without_scope_ok():            # spec §3.4
    ok(CONST_RU, RU)

def test_ru_standard_without_scope_rejected():            # spec §3.1
    r = copy.deepcopy(CONST_RU); del r["tier"]
    bad(r, RU)

def test_ru_gate1_stamp_and_fingerprints_ok():            # spec §7.2/§7.3 (v0.9)
    r = copy.deepcopy(RU_BASE)
    r["gate1_stamp"] = {"hash": "sha256:" + "a" * 64, "by": "operator-1", "at": "2026-07-20T09:14:00Z"}
    r["link_fingerprints"] = {"ADR-0031": "sha256:" + "b" * 64}
    ok(r, RU)

def test_ru_malformed_stamp_hash_rejected():
    r = copy.deepcopy(RU_BASE)
    r["gate1_stamp"] = {"hash": "not-a-hash", "by": "x", "at": "2026-07-20T09:14:00Z"}
    bad(r, RU)

def test_ru_invalid_fingerprint_target_rejected():
    r = copy.deepcopy(RU_BASE)
    r["link_fingerprints"] = {"not a key": "sha256:" + "c" * 64}
    bad(r, RU)

# ---------------------------------------------------------------- Manifest
MAN = yaml.safe_load("""
service: service-orders
version: "1.0"
problem_types:
  conflict: { uri: "urn:problem:conflict", status: 409, title: "Conflict" }
values:
  retention: { decision_log_days: 90 }
audit_common: [event, timestamp, actor]
audit_events:
  - { code: orders.cancelled, ru: FEAT-order-cancellation,
      fields: [{ name: order_id, presence: always }, { name: reason, presence: always }] }
endpoints:
  - { id: cancel_order, method: DELETE, path: "/api/v1/orders/{id}", access: protected,
      ru: FEAT-order-cancellation, emits: [conflict], audits: [orders.cancelled] }
""")

SHARED = yaml.safe_load("""
service: shared
version: "1.0"
vocabularies:
  access_tiers: [public, internal, partner, protected]
""")

def test_manifest_example_a_validates():
    ok(MAN, MANIFEST)

def test_shared_manifest_seed_validates():
    ok(SHARED, MANIFEST)

def test_shared_manifest_rejects_interface_surfaces():    # spec §5.5
    s = copy.deepcopy(SHARED)
    s["endpoints"] = [{"id": "x", "method": "GET", "path": "/x", "access": "public", "ru": "FEAT-x"}]
    bad(s, MANIFEST)

def test_manifest_endpoint_missing_ru_link_rejected():    # spec §5.2 / L18
    m = copy.deepcopy(MAN); del m["endpoints"][0]["ru"]
    bad(m, MANIFEST)

def test_manifest_unknown_key_rejected():                 # no inline conflict-comment culture
    m = copy.deepcopy(MAN); m["CONFLICT_NOTES"] = "300 vs 1800"
    bad(m, MANIFEST)

# ---------------------------------------------------------------- Model
MODEL_A = {
    "id": "order-lifecycle", "kind": "statechart", "initial": "pending",
    "undeclared_event_policy": "ignore",
    "vocabulary": {
        "CONFIRM": "{endpoint:confirm_order}", "CANCEL": "{endpoint:cancel_order}",
        "CATALOG_UPDATED": "{message:catalog_updated}", "FULFILLED": "internal",
        "PAYMENT_LOST": "{message:payment_lost}", "CANCEL_COMPLETE": "internal"},
    "states": {
        "pending": {"on": {"CONFIRM": "processing", "CANCEL": "cancelled"}},
        "processing": {"on": {"CATALOG_UPDATED": "processing", "CANCEL(order_id)": "cancelling",
                              "FULFILLED": "completed", "PAYMENT_LOST": "failed"}},
        "cancelling": {"invariant": "no_new_shipments_dispatched",
                       "on": {"CANCEL_COMPLETE": "cancelled"}},
        "completed": {"type": "final"}, "cancelled": {"type": "final"}, "failed": {"type": "final"}}}

def test_model_example_a_validates():
    ok(MODEL_A, MODEL)

def test_model_missing_undeclared_event_policy_rejected():  # formats.md decision 3
    m = {k: v for k, v in MODEL_A.items() if k != "undeclared_event_policy"}
    bad(m, MODEL)

def test_model_missing_vocabulary_rejected():               # C8 binding is mandatory
    m = {k: v for k, v in MODEL_A.items() if k != "vocabulary"}
    bad(m, MODEL)

# ---------------------------------------------------------------- FEAT / GAP
def test_feat_validates_and_rejects_verification():
    f = {"id": "FEAT-fraud-screening",
         "goal": "Incoming orders are screened by manager-configured fraud rules automatically.",
         "source_ref": "INT-0102#L40-45", "status": "active"}
    ok(f, FG["feat"])
    f2 = dict(f); f2["verification"] = [{"type": "test", "ref": "x"}]
    bad(f2, FG["feat"])                                     # L11 structural backstop

def test_gap_validates_and_resolved_requires_int_anchor():
    g = {"id": "GAP-01J3F8KQZ2ABCDEFGHJKMNPQRS",
         "question": "Cancel bound: 5s or 30s? Transcript says 'quickly'.",
         "severity": "blocking", "raised_by": "analyst",
         "affected": ["RU-draft-01J3F8KQZ2ABCDEFGHJKMNPQRT"], "status": "open"}
    ok(g, FG["gap"])
    g2 = dict(g); g2["status"] = "resolved"                 # resolved w/o resolution → invalid
    bad(g2, FG["gap"])
    g2["resolution"] = {"int_ref": "INT-0103#L5-6", "summary": "5 seconds confirmed."}
    ok(g2, FG["gap"])

# ---------------------------------------------------------------- v0.10
def test_endpoint_success_status_and_planned_ok():
    m = copy.deepcopy(MAN)
    m["endpoints"][0]["outbound"] = {"status": 204, "fields": "none"}
    m["endpoints"].append({"id": "refund_order", "method": "POST", "path": "/api/v1/orders/{id}/refund",
                           "access": "protected", "ru": "FEAT-order-cancellation", "planned": True})
    ok(m, MANIFEST)

def test_endpoint_error_code_as_success_status_rejected():
    m = copy.deepcopy(MAN)
    m["endpoints"][0]["outbound"] = {"status": 409, "fields": "none"}
    bad(m, MANIFEST)

def test_endpoint_legacy_success_status_key_rejected():      # v0.13: retired into outbound.status
    m = copy.deepcopy(MAN); m["endpoints"][0]["success_status"] = 204
    bad(m, MANIFEST)

def test_message_external_inbound_ok_outbound_rejected():   # spec §5.8
    m = copy.deepcopy(MAN)
    m["messages"] = [{"id": "gw_event", "subject": "gateway.member_joined", "direction": "inbound",
                      "payload": "wire::GwMemberJoined", "ru": "FEAT-order-cancellation", "external": True}]
    ok(m, MANIFEST)
    m["messages"][0]["direction"] = "outbound"
    bad(m, MANIFEST)

# ---------------------------------------------------------------- v0.10.1
def test_ru_email_in_stamp_by_rejected():                   # formats §9: handles, never contact info
    r = copy.deepcopy(RU_BASE)
    r["gate1_stamp"] = {"hash": "sha256:" + "a" * 64, "by": "someone@example.com",
                        "at": "2026-07-20T09:14:00Z"}
    bad(r, RU)
    r["gate1_stamp"]["by"] = "mze-runner"
    ok(r, RU)

# ---------------------------------------------------------------- v0.13
def _ep(**over):
    ep = {"id": "cancel_order", "method": "DELETE", "path": "/api/v1/orders/{id}",
          "access": "protected", "ru": "FEAT-order-cancellation"}
    ep.update(over)
    return ep

def _man(ep):
    m = copy.deepcopy(MAN); m["endpoints"] = [ep]; return m

def test_endpoint_declares_both_directions():
    ok(_man(_ep(inbound={"fields": [{"name": "id", "in": "path", "presence": "required",
                                     "type": "string"}]},
                outbound={"status": 200, "fields": [{"name": "order_id", "presence": "always",
                                                     "type": "string"}]})), MANIFEST)

def test_none_is_a_legal_declaration_in_both_directions():
    # `none` is a POSITIVE claim; an absent slot is unfinished work (C10's job).
    ok(_man(_ep(inbound="none", outbound={"status": 204, "fields": "none"})), MANIFEST)
    ok(_man(_ep()), MANIFEST)                               # schema permits absence; C10 does not

def test_outbound_requires_a_status():
    bad(_man(_ep(outbound={"fields": "none"})), MANIFEST)

def test_presence_union_admitted_by_schema_direction_is_c11():
    # Grammar permissive, linter strict: the schema takes the union so C11 can
    # produce a teaching message instead of a parse failure.
    for p in ("always", "never", "required", "optional", "forbidden"):
        ok(_man(_ep(inbound={"fields": [{"name": "amount", "presence": p}]})), MANIFEST)
    bad(_man(_ep(inbound={"fields": [{"name": "amount", "presence": "maybe"}]})), MANIFEST)

def test_nested_and_array_fields():
    ok(_man(_ep(outbound={"status": 200, "fields": [
        {"name": "items", "presence": "always", "type": "array", "items": "object"},
        {"name": "items.id", "presence": "always", "type": "string"},
        {"name": "cancellation", "presence": "always", "type": "object", "nullable": True},
        {"name": "cancellation.at", "presence": "always", "type": "string"}]})), MANIFEST)

def test_bounds_accept_literal_or_value_token():
    for b in (254, "{value:email.max_chars}"):
        ok(_man(_ep(inbound={"fields": [{"name": "email", "presence": "required",
                                         "type": "string", "max_chars": b}]})), MANIFEST)
    bad(_man(_ep(inbound={"fields": [{"name": "email", "presence": "required",
                                      "type": "string", "max_chars": "{vocab:emails}"}]})), MANIFEST)

def test_field_name_pattern_admits_convention_union():
    # C14 decides which convention is legal here; the grammar must not pre-empt it.
    for n in ("order_id", "orderId", "order-id", "OrderId"):
        ok(_man(_ep(outbound={"status": 200,
                              "fields": [{"name": n, "presence": "always"}]})), MANIFEST)
    bad(_man(_ep(outbound={"status": 200,
                           "fields": [{"name": "9lives", "presence": "always"}]})), MANIFEST)

def test_conventions_shared_only_and_defaults_service_only():
    s = copy.deepcopy(SHARED); s["conventions"] = {"field_names": "snake_case"}
    ok(s, MANIFEST)
    s2 = copy.deepcopy(SHARED); s2["defaults"] = {"unknown_fields": "reject"}
    bad(s2, MANIFEST)
    m = copy.deepcopy(MAN); m["conventions"] = {"field_names": "snake_case"}
    bad(m, MANIFEST)
    m2 = copy.deepcopy(MAN); m2["defaults"] = {"unknown_fields": "reject"}
    ok(m2, MANIFEST)
