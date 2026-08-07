"""Test-plan contract (spec §6.3) — the core→adapter half of emission.

The split under test: `plan_model_suite` decides WHAT must be checked; the
emitter role renders only how that reads in its stack, out of process.
Invariants here: the plan is schema-valid and derived purely from the model;
check identity comes from the plan and core refuses an emitter response that
drops, invents, or double-maps a check; emitted paths cannot escape the
consumer root. Rendering semantics (one ignored test per plan check, policy
outcome selection, purity) bind the ADAPTER and live in its own cargo tests;
the committed request/response pair is the seam both sides are pinned to."""

import json
import shutil
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from rqunit.errors import BadConfig
from rqunit.generate import emit_request, plan_model_suite, render_test_plan, targets
from rqunit.config import load as load_config
from rqunit.store import Store

FIXTURES = Path(__file__).parent.parent / "fixtures"
VALID = FIXTURES / "store" / "valid"   # carries MDL-order-lifecycle
REPO = Path(__file__).parent.parent
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


def test_plan_records_the_model_hash_for_staleness():
    store = _store()
    plan = plan_model_suite(store, "order-lifecycle")
    assert plan["model_hash"] == store.models()["order-lifecycle"].content_hash


def test_trace_map_identity_comes_from_the_plan_not_from_parsing_source():
    """Regression: deriving check ids by regexing emitted Rust also matched the
    `shim()` helper, mapping a non-test into the trace map. Identity now flows
    through the emitter's checks mapping, which core validates against the
    plan's census."""
    root = VALID
    store = Store.load(root)
    generated = targets(store, root)
    trace_map = json.loads(generated[root / "spec" / "projections" / "trace-map.json"])["checks"]
    assert not any(key.endswith("::shim") for key in trace_map)
    planned = {c["id"] for m in store.models() for c in plan_model_suite(store, m)["checks"]}
    assert {key.rsplit("::", 1)[1] for key in trace_map} == planned


def test_test_plan_is_a_committed_generated_artifact():
    assert (VALID / "spec" / "projections" / "test-plan.json") in targets(Store.load(VALID), VALID)


# --------------------------------------------- core judges the emitter response

def _tampered(tmp_path, mutate) -> Path:
    root = tmp_path / "store"
    shutil.copytree(VALID, root)
    path = root / "emit-response.json"
    response = json.loads(path.read_text())
    mutate(response)
    path.write_text(json.dumps(response))
    return root


def test_an_unmapped_plan_check_is_a_contract_violation(tmp_path):
    root = _tampered(tmp_path, lambda r: r["checks"].pop())
    with pytest.raises(BadConfig) as caught:
        targets(Store.load(root), root)
    assert "unmapped" in str(caught.value)


def test_an_invented_check_is_a_contract_violation(tmp_path):
    def mutate(response):
        response["checks"].append({"model": "order-lifecycle",
                                   "plan_id": "invented_check",
                                   "id": "pkg::file::invented_check"})
    root = _tampered(tmp_path, mutate)
    with pytest.raises(BadConfig) as caught:
        targets(Store.load(root), root)
    assert "does not contain" in str(caught.value)


def test_a_double_mapped_check_is_a_contract_violation(tmp_path):
    root = _tampered(tmp_path, lambda r: r["checks"].append(dict(r["checks"][0])))
    with pytest.raises(BadConfig) as caught:
        targets(Store.load(root), root)
    assert "twice" in str(caught.value)


def test_an_emitted_path_cannot_escape_the_consumer_root(tmp_path):
    def mutate(response):
        response["files"].append({"path": "../outside.rs", "content": "// escape\n"})
    root = _tampered(tmp_path, mutate)
    with pytest.raises(BadConfig) as caught:
        targets(Store.load(root), root)
    assert "escapes" in str(caught.value)


def test_a_store_with_models_and_no_emitter_is_told_not_silently_bare(tmp_path):
    """`rqunit generate` errors — suites silently not existing is the failure
    mode — while verbs that merely refresh projections regenerate what they
    can (activation must not be walled off by a missing emitter)."""
    from click.testing import CliRunner

    from rqunit.cli.generate import main as generate_main

    root = tmp_path / "store"
    shutil.copytree(VALID, root)
    (root / "rqunit.toml").write_text("[stacks.rust]\n")     # emitter role removed
    result = CliRunner().invoke(generate_main, ["check", "--store", str(root)])
    assert result.exit_code == 2 and "emitter" in result.output
    # the lenient path still produces the store-contract projections
    staged = targets(Store.load(root), root)
    assert staged and all("projections" in str(p) for p in staged)


# --------------------------------------------- the seam both sides are pinned to

def test_committed_emit_requests_are_current():
    """The chain that keeps artifact-mode emission honest: THIS test pins the
    committed request to the live store; the adapter's cargo golden test pins
    the committed response to the committed request. Either link going stale
    is a red build, so the pair cannot drift from the store unnoticed. Every
    committed pair in the repo is swept — a new store joining the convention
    joins the pin."""
    roots = sorted({p.parent for p in REPO.glob("fixtures/store/*/emit-request.json")}
                   | {p.parent for p in REPO.glob("demo/*/emit-request.json")})
    assert roots, "no committed emit-request pairs — this test would pass vacuously"
    for root in roots:
        store = Store.load(root)
        stack = load_config(root).stack("rust")
        committed = json.loads((root / "emit-request.json").read_text())
        assert committed == emit_request(store, stack), (
            f"{root}/emit-request.json is stale — regenerate it (and pipe it "
            "through emit-suite to refresh emit-response.json)")


def test_the_pack_shipped_kit_request_is_inside_the_currency_loop():
    """`rqunit adapter verify` feeds every emitter this fixture; if the plan
    format grows and this copy does not, the kit certifies emitters against a
    request the framework no longer produces. It is pinned to the valid
    store's request (its source) and to the contract schema — nothing else
    validates it."""
    from rqunit.schemas import PACK_DIR

    kit_request = json.loads((PACK_DIR / "kit" / "emit-request.json").read_text())
    schema = (Path(__file__).parent.parent / "src" / "rqunit" / "interfaces"
              / "emit-request.schema.json")
    Draft202012Validator(json.loads(schema.read_text())).validate(kit_request)
    live = emit_request(Store.load(VALID), load_config(VALID).stack("rust"))
    assert kit_request == live, (
        "pack/kit/emit-request.json is stale against its source store — "
        "regenerate it from fixtures/store/valid (and refresh every adapter "
        "kit's emitter expectation)")
