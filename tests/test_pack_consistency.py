"""Pack self-consistency (regression guard for the GAP08 class of defect):
every fact-key shape the manifest schema PERMITS must be REFERENCEABLE under
the token grammar — a schema that can declare a fact the grammar cannot name
ships an internal contradiction no consumer can work around.

Representative shapes are sampled from the schema's own patterns; if a schema
pattern widens, add its new shape here in the same change."""

import pytest

from rqunit.parser.tokens import extract
from rqunit.store import _TOKEN

# (token, schema rule that legitimizes the key shape)
REFERENCEABLE_SHAPES = [
    ("{problem:not-found}", "problem_types propertyNames allow hyphens (RFC 7807 style)"),
    ("{problem:too-many-requests}", "multi-hyphen problem keys"),
    ("{problem:validation}", "plain problem keys"),
    ("{audit:auth.account.deletion_initiated}", "audit codes: dotted with underscores"),
    ("{endpoint:cancel_order}", "surface ids: lowercase + underscore"),
    ("{message:order_cancelled}", "message ids"),
    ("{channel:lobby}", "channel ids"),
    ("{frame:lobby.forced_logout}", "frame refs: channel.frame"),
    ("{vocab:access_tiers}", "vocabulary names"),
    ("{value:tokens.revert_token_ttl_hours}", "dotted value paths"),
    ("{problem:service-billing/payment-failed}", "qualified ref to a hyphenated key"),
    ("{endpoint:service-auth/token_refresh}", "qualified surface ref (hyphenated service slug)"),
]


@pytest.mark.parametrize("token,why", REFERENCEABLE_SHAPES, ids=[t for t, _ in REFERENCEABLE_SHAPES])
def test_schema_legal_key_shapes_are_referenceable(token, why):
    tokens, errors = extract(token)
    assert not errors and len(tokens) == 1, f"{token} must tokenize ({why}); got errors {errors}"
    # the store-side resolver regex must stay in lockstep with the tokenizer
    assert _TOKEN.match(token), f"{token}: store._TOKEN disagrees with parser.tokens (grammar drift)"


@pytest.mark.parametrize("token", [
    "{value:service-orders/retention.decision_log_days}",  # qualified value: forbidden (§5.3)
    "{endpoint:CancelOrder}",                               # uppercase never legal
    "{frame:pong}",                                         # frame needs channel.frame
])
def test_grammar_extension_did_not_loosen_the_malformed_classes(token):
    _, errors = extract(token)
    assert errors, f"{token} must remain malformed"
