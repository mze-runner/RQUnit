"""Path normalization (spec §5.6): the identity that lets a manifest and a
router table agree about which route is which.

Invariant, not census: the same route spelled by any framework normalizes to
one key, and two genuinely different routes never collide."""

import pytest

from rqunit.pathnorm import normalize, placeholder_names

SAME_ROUTE = [
    "/api/v1/orders/{id}",          # axum 0.7+, OpenAPI, Spring
    "/api/v1/orders/:id",           # Express, Rails, older axum
    "/api/v1/orders/<id>",          # Flask
    "/api/v1/orders/<int:id>",      # Flask, typed
    "/api/v1/orders/{id:uuid}",     # axum, typed
    "/api/v1/orders/{order_id}",    # same route, different local name
    "/api/v1/orders/{id}/",         # trailing slash
]


@pytest.mark.parametrize("spelling", SAME_ROUTE)
def test_every_spelling_of_one_route_shares_an_identity(spelling):
    assert normalize(spelling) == normalize(SAME_ROUTE[0])


def test_distinct_routes_do_not_collide():
    distinct = ["/api/v1/orders", "/api/v1/orders/{id}", "/api/v1/orders/{id}/items",
                "/api/v1/orders/{id}/items/{item_id}", "/api/v1/refunds/{id}"]
    assert len({normalize(p) for p in distinct}) == len(distinct)


def test_a_literal_segment_is_never_mistaken_for_a_placeholder():
    assert normalize("/api/v1/orders/latest") == "/api/v1/orders/latest"
    assert placeholder_names("/api/v1/orders/latest") == []


def test_names_survive_normalization_because_c12_needs_them():
    # Identity drops the names; C12 reconciles them against `in: path` fields,
    # which is the only place a placeholder name carries meaning.
    assert placeholder_names("/orders/{order_id}/items/{item_id}") == ["order_id", "item_id"]
    assert placeholder_names("/orders/<int:order_id>") == ["order_id"]
    assert placeholder_names("/orders/{order_id:uuid}") == ["order_id"]
