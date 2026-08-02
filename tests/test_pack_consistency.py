"""Pack self-consistency (regression guard for the GAP08 class of defect):
every fact-key shape the manifest schema PERMITS must be REFERENCEABLE under
the token grammar — a schema that can declare a fact the grammar cannot name
ships an internal contradiction no consumer can work around.

Representative shapes are sampled from the schema's own patterns; if a schema
pattern widens, add its new shape here in the same change."""

from pathlib import Path

import pytest

from rqunit.errors import MalformedRef
from rqunit.parser.tokens import _KEY_ENDPOINT, extract
from rqunit.schemas import load_schema
from rqunit.store import Store

# (token, schema rule that legitimizes the key shape)
REFERENCEABLE_SHAPES = [
    ("{artifact:jwt-access-token}", "shared artifacts registry (v0.14)"),
    ("{artifact:jwt-access-token.iss}", "one claim of an artifact"),
    ("{artifact:shared/jwt-access-token.sub}", "qualified artifact ref"),
    ("{endpoint:get_order.outbound}", "endpoint `outbound` slot (v0.13)"),
    ("{endpoint:get_order.inbound}", "endpoint `inbound` slot (v0.13)"),
    ("{endpoint:get_order.outbound.cost_basis}", "a declared field of a census"),
    ("{endpoint:get_order.outbound.cancellation.at}", "field_name admits dotted nesting"),
    ("{endpoint:list_items.inbound.limit}", "query parameters are part of the accepted surface"),
    ("{endpoint:update_order.inbound.orderId}", "field_name admits the naming-convention union"),
    ("{endpoint:update_order.inbound.order-id}", "field_name admits kebab-case"),
    ("{endpoint:service-billing/get_charge.outbound.card_pan}", "qualified shape ref"),
    ("{problem:not-found}", "problem_types propertyNames allow hyphens (RFC 7807 style)"),
    ("{problem:too-many-requests}", "multi-hyphen problem keys"),
    ("{problem:validation}", "plain problem keys"),
    ("{audit:auth.account.deletion_initiated}", "audit codes: dotted with underscores"),
    ("{endpoint:cancel_order}", "surface ids: lowercase + underscore"),
    ("{message:order_cancelled}", "message ids"),
    ("{channel:tracking}", "channel ids"),
    ("{frame:tracking.shipment_moved}", "frame refs: channel.frame"),
    ("{vocab:access_tiers}", "vocabulary names"),
    ("{value:tokens.revert_token_ttl_hours}", "dotted value paths"),
    ("{problem:service-billing/payment-failed}", "qualified ref to a hyphenated key"),
    ("{endpoint:service-billing/charge_order}", "qualified surface ref (hyphenated service slug)"),
]


@pytest.mark.parametrize("token,why", REFERENCEABLE_SHAPES, ids=[t for t, _ in REFERENCEABLE_SHAPES])
def test_schema_legal_key_shapes_are_referenceable(token, why):
    tokens, errors = extract(token)
    assert not errors and len(tokens) == 1, f"{token} must tokenize ({why}); got errors {errors}"
    # The resolver must accept every shape the tokenizer accepts. UnresolvedRef
    # is fine here — an empty store has nothing to hit — but MalformedRef would
    # mean the two disagree about the grammar itself.
    store = Store(root=Path("."))
    try:
        store.resolve_ref(token)
    except MalformedRef as e:                                   # pragma: no cover - failure path
        pytest.fail(f"{token}: resolver rejects a shape the tokenizer accepts ({e})")
    except Exception:
        pass


def test_field_segment_charset_matches_the_schema():
    """The manifest may declare a field name only if a token can address it.
    Sampling alone missed this once: a schema pattern widened, the grammar did
    not, and the sampled list was not extended in the same change. Couple the
    two directly so widening either side without the other is a red build."""
    schema_pattern = load_schema("manifest")["$defs"]["field_name"]["pattern"]
    segment = "[A-Za-z][A-Za-z0-9_-]*"
    assert segment in schema_pattern, (
        "manifest $defs/field_name widened: extend the token grammar's field "
        "segment in the same change (formats §2)")
    assert segment in _KEY_ENDPOINT.pattern, (
        "token grammar's field segment widened: extend manifest $defs/field_name "
        "in the same change (formats §2)")


@pytest.mark.parametrize("token", [
    "{value:service-orders/retention.decision_log_days}",  # qualified value: forbidden (§5.3)
    "{endpoint:CancelOrder}",                               # uppercase never legal
    "{frame:pong}",                                         # frame needs channel.frame
    "{artifact:JWT}",                                       # uppercase never legal
    "{artifact:a.b.c}",                                     # a claim set is flat
])
def test_grammar_extension_did_not_loosen_the_malformed_classes(token):
    _, errors = extract(token)
    assert errors, f"{token} must remain malformed"
