"""Pack self-consistency (regression guard for the GAP08 class of defect):
every fact-key shape the manifest schema PERMITS must be REFERENCEABLE under
the token grammar — a schema that can declare a fact the grammar cannot name
ships an internal contradiction no consumer can work around.

Representative shapes are sampled from the schema's own patterns; if a schema
pattern widens, add its new shape here in the same change."""

import re
import string
from pathlib import Path

import pytest

from rqunit import ids
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


# --------------------------------------------------------------- id shape
# `ids` is the single source for what a permanent id looks like, but the
# schema patterns are literal strings in checked-in YAML/JSON that nothing
# generates. "Single source" is therefore a claim these tests enforce rather
# than something construction guarantees — the same arrangement, and the same
# reason, as the field-charset coupling above.

def _shipped_schema_texts() -> dict[str, str]:
    """Every schema this pack ships — the checked-in pack YAML AND the pinned
    adapter interface contracts. Discovered, never enumerated: a hand-kept list
    of sites is the thing most likely to go stale, which would defeat the
    coupling it exists to provide."""
    import rqunit
    base = Path(rqunit.__file__).parent
    found = {}
    for directory in (base / "pack" / "schemas", base / "interfaces"):
        for path in sorted(directory.glob("*.json")) + sorted(directory.glob("*.yaml")):
            found[str(path.relative_to(base))] = path.read_text()
    return found


_QUOTED = re.compile(r'"pattern":\s*"((?:[^"\\]|\\.)*)"'      # JSON
                     r"|pattern:\s*\"((?:[^\"\\]|\\.)*)\"")   # YAML flow scalar


def _all_patterns() -> list[tuple[str, str]]:
    """(where, pattern) for every `pattern` in every shipped schema.

    One extractor, because the JSON and YAML quoting rules and the escape
    handling are the fiddly part — a second copy is where the next family's
    sweep silently reads its patterns wrong."""
    out = []
    for where, text in _shipped_schema_texts().items():
        for match in _QUOTED.finditer(text):
            raw = match.group(1) or match.group(2)
            pattern = raw.encode().decode("unicode_escape") if "\\\\" in raw else raw
            out.append((where, pattern))
    return out


def _ru_patterns() -> list[tuple[str, str]]:
    """(where, pattern) for every shipped pattern that mentions a PERMANENT RU
    id. Draft-only patterns are the ULID grammar wearing the same prefix and
    are legitimately narrower, so they are excluded by shape rather than by a
    list of exceptions."""
    permanent_mention = re.compile(r"RU-(?!draft-)")
    return [(where, pattern) for where, pattern in _all_patterns()
            if permanent_mention.search(pattern)]


# A corpus wide enough that a pattern edited by hand cannot agree with `ids` by
# accident: legal shapes, near-misses, and the confusables the alphabet drops.
ID_CORPUS = [
    "RU-0001", "RU-0142", "RU-01A2", "RU-ZZZZ", "RU-A1B2",
    "RU-ORD-0001", "RU-ORD-01A2", "RU-ORDERMGT-ZZZZ", "RU-AUTH-0001",
    "RU-CART-0001", "RU-PYMT-0001",            # segment the sequence can spell
    "RU-01O2", "RU-01I2", "RU-01L2", "RU-01U2",  # excluded characters
    "RU-01a2", "RU-ord-0001", "RU-012", "RU-00012", "RU-",
    "RU-abc123", "RU-0001-ORD", "RU-ORD-ORD-0001", "RU-ORDERMGMT-0001",
    "RU-draft-01J3F8KQZ2ABCDEFGHJKMNPQRS",
]


def test_every_shipped_id_pattern_accepts_exactly_what_the_loader_accepts():
    """The invariant, stated as behaviour rather than as text: for every RU-ish
    string, a schema must reach the same verdict as `ids`. Substring containment
    would pass a pattern hand-widened with an extra alternative — which is the
    drift this exists to catch, so the corpus is compared verdict by verdict.

    Patterns that legitimately accept more than RU ids (a GAP subject may name a
    FEAT; a draft is not a permanent id) are compared only on the RU-permanent
    subset, which is the part `ids` owns."""
    found = _ru_patterns()
    assert found, "no shipped schema mentions an RU id — the sweep found nothing to check"

    truth = re.compile(ids.permanent_pattern("RU"))
    problems = []
    for where, pattern in found:
        compiled = re.compile(pattern)
        for candidate in ID_CORPUS:
            if candidate.startswith("RU-draft-"):
                continue          # drafts are the ULID grammar, not this one
            if bool(truth.fullmatch(candidate)) or not compiled.fullmatch(candidate):
                continue
            problems.append(f"{where} accepts {candidate!r}, which is not a permanent RU id")
    assert not problems, (
        "shipped schema pattern(s) drifted from `ids.permanent_pattern('RU')`:\n  "
        + "\n  ".join(problems)
        + "\n  Regenerate them from `ids` in the change that alters the grammar.")


def test_every_shipped_id_pattern_still_accepts_every_legal_id():
    """The other direction: a NARROWED pattern refuses ids the loader admits,
    which is how a store becomes unloadable by its own schema."""
    truth = re.compile(ids.permanent_pattern("RU"))
    legal = [c for c in ID_CORPUS if truth.fullmatch(c)]
    problems = [f"{where} refuses {candidate!r}"
                for where, pattern in _ru_patterns()
                for candidate in legal
                if not re.compile(pattern).fullmatch(candidate)]
    assert not problems, "shipped schema pattern(s) narrower than the grammar:\n  " + "\n  ".join(problems)


# Both intent forms, near-misses on each, and the confusables the alphabet
# drops. Wide enough that a pattern edited by hand cannot agree by accident.
INTENT_CORPUS = [
    "INT-0057",                            # what an early store carries
    "INT-01J3F8KQZ2ABCDEFGHJKMNPQRS",      # what capture writes now
    "INT-01K1TESTAAAAAAAAAAAAAAAAAA",
    "INT-01O3F8KQZ2ABCDEFGHJKMNPQRS",      # O is not in the alphabet
    "INT-01I3F8KQZ2ABCDEFGHJKMNPQRS",      # nor is I
    "INT-01J3F8KQZ2ABCDEFGHJKMNPQR",       # 25 characters
    "INT-01J3F8KQZ2ABCDEFGHJKMNPQRST",     # 27
    "INT-057", "INT-00570", "int-0057",
    "INT-01j3f8kqz2abcdefghjkmnpqrs",      # case is never folded
]


def _intent_patterns() -> list[tuple[str, str]]:
    """(where, pattern) for every shipped pattern mentioning an intent id."""
    return [(where, pattern) for where, pattern in _all_patterns()
            if "INT-" in pattern]


def test_every_shipped_intent_pattern_agrees_with_the_grammar():
    """`source_ref` is the provenance link a Gate 1 reviewer follows, and three
    schemas spell its anchor by hand. Compared by VERDICT, not by substring: a
    containment check passes a pattern that carries the right text anchored
    wrongly, and reddens on a semantically identical respelling — so it would
    police spelling while missing the defect."""
    found = _intent_patterns()
    assert found, "no shipped schema mentions an intent id"
    truth = re.compile(ids.INTENT_PATTERN)
    problems = []
    for where, pattern in found:
        compiled = re.compile(pattern)
        for candidate in INTENT_CORPUS:
            # Schema patterns carry the ANCHOR suffix; compare on the id alone
            # by appending the smallest legal anchor.
            expected = bool(truth.fullmatch(candidate))
            actual = bool(compiled.fullmatch(f"{candidate}#L1"))
            if expected != actual:
                problems.append(f"{where}: {candidate!r} — grammar says "
                                f"{expected}, schema says {actual}")
    assert not problems, ("shipped intent pattern(s) drifted from "
                          "`ids.INTENT_PATTERN`:\n  " + "\n  ".join(problems))


def test_the_intent_grammar_admits_both_forms_and_nothing_else():
    """Both forms are legal forever: an intent is immutable and every RU
    compiled from one cites it, so re-identifying one rewrites the provenance of
    requirements that are already stamped."""
    pattern = re.compile(ids.INTENT_PATTERN)
    accepted = {c for c in INTENT_CORPUS if pattern.fullmatch(c)}
    assert accepted == {"INT-0057", "INT-01J3F8KQZ2ABCDEFGHJKMNPQRS",
                        "INT-01K1TESTAAAAAAAAAAAAAAAAAA"}, sorted(accepted)


def test_the_draft_segment_field_pins_the_segment_grammar():
    """The `segment` field's pattern is a hand copy of `ids.SEGMENT_ALONE`, and
    the RU-id sweep above cannot see it — it carries no `RU-` prefix. Left
    uncoupled, widening or narrowing the segment rule gives a draft the schema
    admits whose name `format_id` then refuses, with no diagnosis at all."""
    pattern = load_schema("ru")["properties"]["segment"]["pattern"]
    assert pattern == ids.SEGMENT_ALONE
    for name in ("ORD", "AUTH", "ORDS", "CART", "PYMT", "X", "ord", "0RD", "ORDERMGMT"):
        assert bool(re.match(pattern, name)) == ids.is_segment(name), name


def test_the_status_conditional_pins_the_permanent_shape_too():
    """The `allOf` branch that forbids a draft id on an active RU is the rule
    that makes activation meaningful; it is also the easiest one to miss when
    the grammar moves, because it lives away from `properties`."""
    branches = load_schema("ru")["allOf"]
    permanent = [b for b in branches
                 if b.get("if", {}).get("properties", {}).get("status", {}).get("enum")
                 and "properties" in b.get("then", {})]
    assert permanent, "the active/superseded/retired id branch is gone"
    for branch in permanent:
        assert branch["then"]["properties"]["id"]["pattern"] == ids.permanent_pattern("RU")


def test_the_regex_alphabet_and_the_string_alphabet_are_the_same_set():
    """`SEQ_PATTERN` spells the alphabet in ranges for readability inside
    schema patterns; `ALPHABET` spells it out for the arithmetic. Two spellings
    of one set is a drift class, so they are coupled here rather than by eye."""
    sequence = re.compile(f"^{ids.SEQ_PATTERN}$")
    for char in string.digits + string.ascii_uppercase + string.ascii_lowercase:
        run = char * ids.SEQ_WIDTH
        assert bool(sequence.match(run)) == (char in ids.ALPHABET), char
