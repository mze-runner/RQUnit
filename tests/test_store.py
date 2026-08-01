"""TASK-003 acceptance: typed loading, determinism, one broken fixture per
error class, §5.3 v0.10 reference resolution, incremental mode."""

from pathlib import Path

import pytest

from rqunit.errors import (
    FilenameIdMismatch,
    MalformedRef,
    MalformedYaml,
    SchemaInvalid,
    UnknownArtifact,
    UnresolvedRef,
)
from rqunit.store import Store

FIXTURES = Path(__file__).parent.parent / "fixtures" / "store"
VALID = FIXTURES / "valid"


@pytest.fixture(scope="module")
def store() -> Store:
    return Store.load(VALID)


# ------------------------------------------------------------ loading

def test_valid_store_loads_every_artifact_type(store):
    assert [r.id for r in store.rus()] == ["RU-0002", "RU-0142"]
    assert [f.id for f in store.features()] == ["FEAT-billing", "FEAT-order-cancellation"]
    assert [g.id for g in store.gaps()] == ["GAP-01J3F8KQZ2ABCDEFGHJKMNPQRS"]
    assert sorted(store.manifests()) == ["service-billing", "service-orders", "shared"]
    assert list(store.models()) == ["order-lifecycle"]
    assert store.intents() == ["INT-0057"]


def test_constitutional_tier_surfaces_on_the_accessor(store):
    by_id = {r.id: r for r in store.rus()}
    assert by_id["RU-0002"].tier == "constitutional"
    assert by_id["RU-0142"].tier == "standard"


def test_manifests_and_models_carry_content_hashes(store):
    for m in store.manifests().values():
        assert m.content_hash.startswith("sha256:") and len(m.content_hash) == 71
    assert store.models()["order-lifecycle"].content_hash.startswith("sha256:")


def test_loading_is_deterministic():
    a, b = Store.load(VALID), Store.load(VALID)
    assert [r.raw for r in a.rus()] == [r.raw for r in b.rus()]
    assert {s: m.content_hash for s, m in a.manifests().items()} == \
           {s: m.content_hash for s, m in b.manifests().items()}


@pytest.mark.parametrize(
    "broken,error",
    [
        ("filename_id_mismatch", FilenameIdMismatch),
        ("malformed_yaml", MalformedYaml),
        ("schema_invalid", SchemaInvalid),
        ("unknown_artifact", UnknownArtifact),
        ("manifest_service_mismatch", FilenameIdMismatch),
        ("model_id_mismatch", FilenameIdMismatch),
    ],
)
def test_broken_store_raises_typed_error(broken, error):
    with pytest.raises(error):
        Store.load(FIXTURES / "broken" / broken)


def test_incremental_mode_parses_only_the_changed_files():
    changed = [VALID / "spec" / "ru" / "RU-0142.yaml"]
    partial = Store.load(VALID, changed=changed)
    assert [r.id for r in partial.rus()] == ["RU-0142"]
    assert partial.manifests() == {} and partial.models() == {}


# ------------------------------------------------------------ resolution (§5.3 v0.10)

def test_resolve_unqualified_kinds_in_scope(store):
    assert store.resolve_ref("{value:retention.decision_log_days}", "service-orders").value == 90
    assert store.resolve_ref("{endpoint:cancel_order}", "service-orders").value["method"] == "DELETE"
    assert store.resolve_ref("{problem:conflict}", "service-orders").value["status"] == 409
    assert store.resolve_ref("{audit:orders.cancelled}", "service-orders").value["code"] == "orders.cancelled"
    assert store.resolve_ref("{message:order_cancelled}", "service-orders").value["direction"] == "outbound"
    assert store.resolve_ref("{channel:tracking}", "service-orders").value["upgrade_path"] == "/ws"
    assert store.resolve_ref("{frame:tracking.pong}", "service-orders").value["payload"] == "ws::Pong"


def test_resolve_unqualified_falls_back_to_shared(store):
    resolved = store.resolve_ref("{vocab:access_tiers}", "service-orders")
    assert resolved.service == "shared" and "protected" in resolved.value


def test_resolve_qualified_hits_only_the_named_manifest(store):
    resolved = store.resolve_ref("{endpoint:service-billing/charge}", "service-orders")
    assert resolved.service == "service-billing"


def test_resolve_qualified_never_falls_back(store):
    # cancel_order exists in service-orders (the scope) — a qualified miss in
    # service-billing must NOT silently bind to it.
    with pytest.raises(UnresolvedRef):
        store.resolve_ref("{endpoint:service-billing/cancel_order}", "service-orders")


def test_resolve_qualified_value_is_malformed(store):
    with pytest.raises(MalformedRef):
        store.resolve_ref("{value:service-orders/retention.decision_log_days}", "service-billing")


@pytest.mark.parametrize(
    "token",
    ["{endpoints:cancel_order}", "{endpoint:}", "{endpoint:{value:x}}", "endpoint:cancel_order"],
)
def test_malformed_tokens_are_distinct_from_unresolved(store, token):
    with pytest.raises(MalformedRef):
        store.resolve_ref(token, "service-orders")


def test_unresolved_reference_raises(store):
    with pytest.raises(UnresolvedRef):
        store.resolve_ref("{endpoint:launch_missiles}", "service-orders")
