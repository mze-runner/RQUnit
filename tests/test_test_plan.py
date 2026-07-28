"""Test-plan contract (spec §6.3) — Phase II Contract 2.

The split under test: `plan_model_suite` decides WHAT must be checked;
`emit_rust_suite` decides only how it reads in Rust. Invariants: the plan is
schema-valid and derived purely from the model; emission is a pure function of
the plan (so a second emitter cannot drift semantically); check identity comes
from the plan rather than from parsing emitted source; and the committed Rust
suites are unchanged by the refactor."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from rqunit.generate import (
    emit_rust_suite,
    plan_model_suite,
    render_model_suite,
    render_test_plan,
    targets,
)
from rqunit.store import Store

FIXTURES = Path(__file__).parent.parent / "fixtures"
VALID = FIXTURES / "store" / "valid"   # carries MDL-order-lifecycle
SCHEMA = (Path(__file__).parent.parent / "src" / "rqunit" / "interfaces"
          / "test-plan.schema.json")


def _store() -> Store:
    return Store.load(VALID)


def test_plan_matches_the_pinned_contract():
    store = _store()
    payload = json.loads(render_test_plan(store))
    Draft202012Validator(json.loads(SCHEMA.read_text())).validate(payload)
    assert payload["contract_version"] == 1
    assert {m["model"] for m in payload["models"]} == set(store.models())


def test_plan_carries_every_check_class_in_emission_order():
    plan = plan_model_suite(_store(), "order-lifecycle")
    kinds = [c["kind"] for c in plan["checks"]]
    assert set(kinds) <= {"transition", "rejection", "invariant"}
    assert kinds == sorted(kinds, key=lambda k: ["transition", "rejection", "invariant"].index(k))
    transitions = [c for c in plan["checks"] if c["kind"] == "transition"]
    assert transitions and all({"from", "event", "to"} <= set(c) for c in transitions)


def test_rejection_expectation_follows_the_models_policy():
    store = _store()
    for model_id, model in store.models().items():
        plan = plan_model_suite(store, model_id)
        expected = "ignored" if model.raw["undeclared_event_policy"] == "ignore" else "error"
        rejections = [c for c in plan["checks"] if c["kind"] == "rejection"]
        assert all(c["expect"] == expected for c in rejections)


def test_emission_is_a_pure_function_of_the_plan():
    """An emitter must not reach past the plan — otherwise a second language
    could silently assert something different from the first."""
    store = _store()
    plan = plan_model_suite(store, "order-lifecycle")
    assert emit_rust_suite(plan) == emit_rust_suite(json.loads(json.dumps(plan)))
    assert emit_rust_suite(plan) == render_model_suite(store, "order-lifecycle")


def test_every_plan_check_becomes_exactly_one_test():
    plan = plan_model_suite(_store(), "order-lifecycle")
    suite = emit_rust_suite(plan)
    assert suite.count("#[test]") == len(plan["checks"])
    for check in plan["checks"]:
        assert f"fn {check['id']}()" in suite


def test_trace_map_identity_comes_from_the_plan_not_from_parsing_source():
    """Regression: deriving check ids by regexing emitted Rust also matched the
    `shim()` helper, mapping a non-test into the trace map."""
    root = VALID
    store = Store.load(root)
    generated = targets(store, root)
    trace_map = json.loads(generated[root / "spec" / "projections" / "trace-map.json"])["checks"]
    assert not any(key.endswith("::shim") for key in trace_map)
    planned = {c["id"] for m in store.models() for c in plan_model_suite(store, m)["checks"]}
    assert {key.rsplit("::", 1)[1] for key in trace_map} == planned


def test_test_plan_is_a_committed_generated_artifact():
    assert (VALID / "spec" / "projections" / "test-plan.json") in targets(Store.load(VALID), VALID)


def test_plan_records_the_model_hash_for_staleness():
    store = _store()
    plan = plan_model_suite(store, "order-lifecycle")
    assert plan["model_hash"] == store.models()["order-lifecycle"].content_hash
