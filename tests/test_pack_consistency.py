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


def test_spec_version_matches_the_specification_status_line():
    """The pack pin records the SPEC version, so that constant must be the one
    the specification actually announces. Two version numbers for one thing is
    how a store ends up pinned to a vocabulary that was never published — which
    is exactly what happened while the pin recorded the PACKAGE version and the
    two had silently drifted apart by one minor."""
    import re

    from rqunit.schemas import SPEC_VERSION

    spec = (Path(__file__).parent.parent / "docs" / "ru-framework-spec.md").read_text()
    status = spec.split("\n", 3)[2]                     # the **Status:** line
    announced = re.search(r"v(\d+\.\d+\.\d+)", status)
    assert announced, f"no version in the status line: {status[:80]}"
    assert announced.group(1) == SPEC_VERSION, (
        f"specification announces v{announced.group(1)}, schemas.SPEC_VERSION is "
        f"{SPEC_VERSION} — bump both in the same change")


def test_tool_and_spec_versions_are_allowed_to_differ():
    """Not an accident to be corrected: a tool fix changes no vocabulary, and
    forcing a spec revision for one would make consumers re-read a document
    that did not change."""
    from rqunit.schemas import SPEC_VERSION, installed_version

    assert SPEC_VERSION and installed_version()          # both exist, independently


def test_no_shipped_text_advertises_a_stale_conformance_range():
    """A rule catalogue quoted as a range rots the moment a rule is added, and
    the quote is what a consumer reads BEFORE the rules — the CLI's own help,
    the handbook, the skills the tool emits into a consumer repository. This
    fired for real: two audit rules shipped and `rqunit conformance --help`
    still advertised the ceiling from before them, so the newest capability was
    invisible at the surface that introduces it. Assert the ceiling, not the
    census: the highest rule the reconciler can actually emit.

    Dated design papers are exempt, as everywhere else — a snapshot describes
    the ceiling of its own day, and editing one to satisfy a linter would make
    it lie about when it was written."""
    import re
    import subprocess

    from rqunit.conformance import _SUGGESTION

    highest = max(int(rule[2:]) for rule in _SUGGESTION)
    root = Path(__file__).parent.parent
    tracked = subprocess.run(
        ["git", "ls-files", "-z", "*.py", "*.md", "*.yaml"],
        cwd=root, capture_output=True, text=True, check=True,
    ).stdout.split("\0")
    pattern = re.compile(r"CF1\s*[–-]\s*CF(\d+)")
    dated = re.compile(r"\*\*Status:\*\*\s*written \d{4}-\d{2}-\d{2}")

    stale = []
    for name in filter(None, tracked):
        path = root / name
        if not path.is_file():
            continue
        text = path.read_text()
        if dated.search("\n".join(text.splitlines()[:8])):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for m in pattern.finditer(line):
                if int(m.group(1)) != highest:
                    stale.append(f"{name}:{lineno} says {m.group(0)}")
    assert not stale, (
        f"the reconciler emits up to CF{highest}; these advertise a different ceiling:\n  "
        + "\n  ".join(stale)
    )
