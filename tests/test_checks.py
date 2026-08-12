"""The consistency-check fixture harness — every registered check has a pass
store that is clean and a fail store that is red for its reason alone — plus
normalizer unit tests, and the invariant that a valid store stays green."""

import shutil
from pathlib import Path

import pytest

from rqunit.checks.base import discover, run_checks
from rqunit.errors import UnresolvedRef
from rqunit.checks.normalize import content_words, lemma
from rqunit.store import Store

FIXTURES = Path(__file__).parent.parent / "fixtures" / "checks"
CHECKS = [f"C{i}" for i in range(1, 18)]


def _run(code: str, kind: str):
    store = Store.load(FIXTURES / code / kind)
    return [v for v in run_checks(store, only=code) if v.rule == code]


def test_registry_covers_every_built_check():
    assert sorted(discover(), key=lambda c: int(c[1:])) == CHECKS


@pytest.mark.parametrize("code", CHECKS)
def test_pass_store_is_clean(code):
    assert _run(code, "pass") == []


@pytest.mark.parametrize("code", CHECKS)
def test_fail_store_is_red(code):
    violations = _run(code, "fail")
    assert len(violations) >= 2, [v.message for v in violations]
    for v in violations:
        assert v.message and v.suggestion


# ------------------------------------------------------------ per-check teeth

def test_c1_distinguishes_conflict_from_duplicate():
    severities = {v.severity for v in _run("C1", "fail")}
    assert severities == {"error", "warning"}  # reordered conflict + verbatim duplicate


def test_c1_lets_decomposition_through():
    """Sharing a trigger is the normal case, not a smell: §2.1 makes each
    acceptance criterion exactly one RU, so a dozen may hang off one endpoint.
    Until v0.14 C1 read "different response" as "conflict" and reported every
    one of them."""
    assert _run("C1", "pass") == []


def test_c1_names_the_two_things_that_actually_contradict():
    messages = {v.artifact: v.message for v in _run("C1", "fail")}
    assert "two bounds" in messages["RU-0002"]        # one obligation, two numbers
    assert "denies" in messages["RU-0004"]            # negation
    assert "duplicate" in messages["RU-0003"]


def test_c1_documented_paraphrase_miss_stays_a_miss():
    # The pass store IS the donor-mandated paraphrase pair — asserting the known
    # limitation keeps the check honest. If this ever fails, C1 got smarter:
    # update the docs, not the check.
    assert _run("C1", "pass") == []


def test_c4_reports_template_normalized_duplicate():
    assert any("template-normalized" in v.message for v in _run("C4", "fail"))


def test_c7_is_finding_class_only():
    violations = _run("C7", "fail")
    assert violations and all(v.severity == "finding" for v in violations)
    assert any("shared value limits.body_bytes" in v.message for v in violations)


def test_c9_covers_all_error_classes():
    messages = " | ".join(v.message for v in _run("C9", "fail"))
    assert "2 outbound declarers" in messages
    assert "no in-store outbound declarer" in messages
    assert "disagrees with the declarer" in messages
    assert "marked external, but subject" in messages


# ------------------------------------------------------------ normalizer unit

def test_normalizer_collides_reorderings():
    a = content_words("a user calls {endpoint:cancel_order}")
    b = content_words("{endpoint:cancel_order} is called by a user")
    assert a == b


def test_normalizer_keeps_paraphrases_apart():
    assert content_words("a user submits an order") != content_words("a user places an order")


def test_lemma_is_deliberately_dumb_but_stable():
    assert lemma("calls") == lemma("called") == lemma("calling") == "call"
    assert lemma("is") == "is"  # too short to strip


# ------------------------------------------------------------ G3 on the real store

# Real-store tests assert INVARIANTS the framework guarantees, never
# point-in-time state: warnings are visible debt BY DESIGN (asserting their
# absence contradicts §6.4/§6.7 and turns legitimate store growth into a
# commit blocker — reproduced live during the batch-1 Gate 1 sitting).

def test_a_valid_store_has_no_check_errors():
    store = Store.load(Path(__file__).parent.parent / "fixtures" / "store" / "valid")
    errors = [v for v in run_checks(store) if v.severity == "error"]
    assert errors == [], [f"{v.rule}: {v.artifact}: {v.message}" for v in errors]


def test_c7_stays_finding_class():
    """Orphan facts are a migration burn-down: reported, never blocking. The
    COUNT is consumer state and is deliberately not asserted."""
    store = Store.load(Path(__file__).parent.parent / "fixtures" / "store" / "valid")
    assert all(v.severity == "finding" for v in run_checks(store, only="C7"))


# ------------------------------------------------------------ v0.13 surfaces

def test_c10_treats_none_as_a_declaration_not_an_omission():
    """The distinction the whole rule exists for: `none` is a claim an extractor
    can falsify, an absent slot is unfinished work."""
    assert _run("C10", "pass") == []                       # the pass store uses `none` in both slots
    assert any("declares no `inbound`" in v.message for v in _run("C10", "fail"))
    assert any("declares no `outbound`" in v.message for v in _run("C10", "fail"))


def test_c10_does_not_exempt_planned_surfaces():
    planned = [v for v in _run("C10", "fail") if "bulk_refund" in v.artifact]
    assert planned, "a planned surface whose shape is unstated has not been designed"


def test_c11_rejects_each_vocabulary_in_the_wrong_direction():
    messages = " ".join(v.message for v in _run("C11", "fail"))
    assert "belongs to outbound shapes" in messages       # `never` used inbound
    assert "in: query" in messages                        # client-supplied marker used outbound


def test_c11_message_explains_why_presence_and_nullable_differ():
    nullable = [v for v in _run("C11", "fail") if "nullable" in v.message]
    assert nullable and any("has no value to be null" in v.suggestion for v in nullable)


def test_c12_reconciles_both_directions_of_the_path_binding():
    messages = " ".join(v.message for v in _run("C12", "fail"))
    assert "has no `in: path` field" in messages          # template names it, census does not
    assert "no such placeholder" in messages              # census names it, template does not
    assert "more than once" in messages                   # duplicate placeholder


def test_c13_is_silent_when_no_convention_is_declared():
    """An absent `conventions` table means unenforced — a store that has not
    opted in must not be reddened by someone else's house standard."""
    store = Store.load(FIXTURES / "C11" / "fail")          # no shared manifest, no conventions
    assert [v for v in run_checks(store, only="C13")] == []


def test_c13_checks_each_dotted_segment_of_a_nested_field():
    assert any("unitPrice" in v.message for v in _run("C13", "fail"))


# ------------------------------------------------ v0.14 emissions get shapes

def test_c6_names_the_key_a_misfiled_id_actually_belongs_to():
    """The split's whole point: `emits` and `audits` were one list resolved by
    trying each registry, so a misfiled id read as 'unknown' rather than
    'wrong key'."""
    messages = [v.message for v in _run("C6", "fail")]
    assert any("is not a declared problem type — it is an audit code" in m for m in messages)
    assert any("`publishes` names" in m for m in messages)


def test_c6_rejects_an_audit_record_promising_a_forbidden_field(tmp_path):
    """Credential material in an evidence trail is the audit equivalent of a
    mass-assignment hole, and the forbidden list is declared store-wide so
    omitting it is visible rather than a per-event oversight."""
    root = tmp_path / "s"
    shutil.copytree(FIXTURES / "C6" / "pass", root)
    (root / "spec" / "manifests" / "shared.manifest.yaml").write_text(
        'service: shared\nversion: "1.0"\naudit_forbidden: [password, raw_token]\n')
    manifest = root / "spec" / "manifests" / "service-orders.manifest.yaml"
    manifest.write_text(manifest.read_text().replace(
        "      - { name: order_id, presence: always, type: string }",
        "      - { name: order_id, presence: always, type: string }\n"
        "      - { name: password, presence: always, type: string }"))
    violations = [v for v in run_checks(Store.load(root), only="C6") if v.rule == "C6"]
    assert violations and "forbids it in every audit record" in violations[0].message


def test_c11_judges_an_audit_census_by_the_outbound_vocabulary(tmp_path):
    """A record is minted, never accepted — so `forbidden` is the wrong claim
    to make about it, and one census grammar means one rule catches that."""
    root = tmp_path / "s"
    shutil.copytree(FIXTURES / "C6" / "pass", root)
    manifest = root / "spec" / "manifests" / "service-orders.manifest.yaml"
    manifest.write_text(manifest.read_text().replace(
        "      - { name: order_id, presence: always, type: string }",
        "      - { name: order_id, presence: forbidden, type: string }"))
    violations = [v for v in run_checks(Store.load(root), only="C11") if v.rule == "C11"]
    assert violations and "belongs to inbound shapes" in violations[0].message


def test_c11_judges_an_artifact_census_and_allows_only_it_a_where(tmp_path):
    """Artifacts were the one census in the manifest that nothing visited — and
    the slot holding the credential shapes. Two halves to the fix: the census is
    judged (a credential is minted, so an inbound presence value asserts nothing),
    and `where` survives, because placement inside an encoded structure is real
    here and meaningless on a payload."""
    flagged = [v for v in _run("C11", "fail")
               if v.artifact.startswith("shared:artifacts.")]

    assert flagged, "the artifact census is visited at all"
    messages = " ".join(v.message for v in flagged)
    assert "belongs to inbound shapes" in messages
    assert "in: query" in messages                    # minted: nothing is client-supplied
    assert "`where`" not in messages                  # legal here, and only here
    assert all("minted, never accepted" in v.suggestion
               for v in flagged if "presence" in v.message)


def test_c11_still_rejects_a_where_on_a_surface_census(tmp_path):
    """The artifact exemption must not become a general one — the guard it
    replaced was unconditional, and on a payload the position IS the field name."""
    root = tmp_path / "s"
    shutil.copytree(FIXTURES / "C11" / "pass", root)
    manifest = root / "spec" / "manifests" / "service-orders.manifest.yaml"
    manifest.write_text(manifest.read_text().replace(
        "{ name: order_id,   in: path, presence: required, type: string }",
        "{ name: order_id, in: path, presence: required, type: string, where: header }"))

    violations = [v for v in run_checks(Store.load(root), only="C11") if v.rule == "C11"]
    assert any("on a surface census" in v.message for v in violations), \
        [v.message for v in violations]


def test_c17_reports_each_way_a_tier_can_fail_to_bind():
    """C5 validates membership on both sides and never relates them, so all three
    of these passed: a tier in use that nothing describes, a tier two credentials
    claim, and a tier declared open while a credential claims it."""
    by_tier = {v.artifact: v.message for v in _run("C17", "fail")}

    assert "no artifact declares it" in by_tier["shared:access_tiers.refresh"]
    assert "claimed by 2 artifacts" in by_tier["shared:access_tiers.protected"]
    assert "credential-free" in by_tier["shared:access_tiers.public"]


def test_c17_names_both_remedies_for_an_unbound_tier():
    """Turning green stores red needs the escape valve visible in the message:
    declare the credential, or declare that there is none. The second is a claim
    worth having on the record, not a waiver."""
    unbound = next(v for v in _run("C17", "fail")
                   if v.artifact == "shared:access_tiers.refresh")

    assert "fields: none" in unbound.suggestion          # the opaque-credential answer
    assert "credential_free_tiers" in unbound.suggestion  # the genuinely-open answer


def test_c17_spares_a_tier_no_surface_uses(tmp_path):
    """A vocabulary may run ahead of the surfaces that will use it. Demanding a
    credential for a tier nothing serves would enforce target state."""
    root = tmp_path / "s"
    shutil.copytree(FIXTURES / "C17" / "pass", root)
    shared = root / "spec" / "manifests" / "shared.manifest.yaml"
    shared.write_text(shared.read_text().replace(
        "access_tiers: [public, internal, protected, scoped, refresh]",
        "access_tiers: [public, internal, protected, scoped, refresh, partner]"))

    assert [v for v in run_checks(Store.load(root), only="C17") if v.rule == "C17"] == []


def test_an_opaque_credential_binds_its_tier_and_resolves_no_members(tmp_path):
    """`fields: none` exists so a total binding is possible without inventing
    internals for a token that has none. It must bind, and it must not be
    mistaken for a census with members."""
    store = Store.load(FIXTURES / "C17" / "pass")

    assert [v for v in run_checks(store, only="C17") if v.rule == "C17"] == []
    assert store.resolve_ref("{artifact:refresh-token}").value is not None
    with pytest.raises(UnresolvedRef):
        store.resolve_ref("{artifact:refresh-token.sub}")


def test_c14_is_finding_class_and_spares_reads_and_planned_surfaces():
    """HTTP method is a heuristic for mutation — POST /search is routine — so an
    error here would false-positive on real designs and teach gate-avoidance."""
    assert _run("C14", "pass") == []                  # GET and `planned` both spared
    violations = _run("C14", "fail")
    assert violations and all(v.severity == "finding" for v in violations)
    assert all("RU-0002" in v.suggestion for v in violations)


def test_c5_rejects_a_field_carrying_an_undeclared_artifact(tmp_path):
    """A census stops at an encoding boundary, so `artifact:` is the only way to
    say what is inside the string — and it must name something that exists."""
    root = tmp_path / "s"
    shutil.copytree(FIXTURES.parent / "store" / "valid", root)
    manifest = root / "spec" / "manifests" / "service-billing.manifest.yaml"
    manifest.write_text(manifest.read_text().replace(
        "artifact: session-token", "artifact: no-such-artifact"))
    violations = [v for v in run_checks(Store.load(root), only="C5") if v.rule == "C5"]
    assert violations and "which no shared manifest declares" in violations[0].message


def test_c11_rejects_placement_on_a_surface_census(tmp_path):
    """`where` is JWS placement inside an encoded artifact. On a payload the
    position IS the field name."""
    root = tmp_path / "s"
    shutil.copytree(FIXTURES / "C6" / "pass", root)
    manifest = root / "spec" / "manifests" / "service-orders.manifest.yaml"
    manifest.write_text(manifest.read_text().replace(
        "      - { name: order_id, presence: always, type: string }",
        "      - { name: order_id, presence: always, type: string, where: claims }"))
    violations = [v for v in run_checks(Store.load(root), only="C11") if v.rule == "C11"]
    assert violations and "on a surface census" in violations[0].message


def test_c13_survives_a_none_census(tmp_path):
    """Regression: C13 iterated `fields: none` as a STRING, walking its
    characters. No fixture store had both a `conventions` table and a `none`
    census, so the path was never taken until the demo store had both."""
    root = tmp_path / "s"
    shutil.copytree(FIXTURES / "C13" / "pass", root)
    manifest = root / "spec" / "manifests" / "service-orders.manifest.yaml"
    manifest.write_text(manifest.read_text().replace(
        "    outbound:\n      status: 200\n      fields:\n"
        "        - { name: items,          presence: always, type: array, items: object }\n"
        "        - { name: items.unit_price, presence: always, type: integer }",
        "    outbound: { status: 204, fields: none }"))
    violations = [v for v in run_checks(Store.load(root), only="C13") if v.rule == "C13"]
    assert violations == []          # nothing to name, and nothing to crash on


# ------------------------------------------------------------ C15 / shims

def test_c15_names_every_defect_class():
    violations = _run("C15", "fail")
    assert any("not a model in this store" in v.message for v in violations)
    assert any("registered more than once" in v.message for v in violations)
    assert any("is not a table" in v.message for v in violations)
    assert all("§6.3" in v.suggestion for v in violations)


def test_a_malformed_registration_is_reported_never_dropped():
    """A bare `- MDL-x` is the shape a hurried consumer writes. Filtering it
    out would leave the model reading as unregistered and the consumer
    chasing an L21 warning about a shim they believe they just registered."""
    from rqunit.shims import load_shims, registered_models

    root = FIXTURES / "C15" / "fail"
    assert any(not isinstance(e, dict) for e in load_shims(root))   # kept
    assert "payment-capture" not in registered_models(root)          # registers nothing
    assert any("is not a table" in v.message for v in _run("C15", "fail"))


def test_c15_accepts_the_mdl_prefix_either_way(tmp_path):
    """`MDL-order-lifecycle` and `order-lifecycle` name one model; a store
    that spells them differently in two entries has still registered it
    twice."""
    from rqunit.shims import registered_models

    assert registered_models(FIXTURES / "C15" / "pass") == {"order-lifecycle",
                                                            "payment-capture"}


def test_an_unregistered_model_contributes_no_mechanical_depth():
    """The last place declared depth could exceed provable depth: a suite
    that cannot execute is not depth, and L21 must say so by name."""
    from rqunit.lints.l21 import violation_reason

    rule = {"require": {"min_mechanical": 2}}
    entries = [{"type": "test", "ref": "svc::t::a"},
               {"type": "model", "ref": "MDL-order-lifecycle"}]
    assert violation_reason(rule, entries) is None            # shim registered
    reason = violation_reason(rule, entries, unshimmed=frozenset({"order-lifecycle"}))
    assert reason and "no registered shim" in reason and "shims.yaml" in reason


def test_c16_catches_the_edit_that_cannot_be_undone():
    """A rename and a removal look identical from the registry: the name stops
    being declared while ids still carry it. That is the violation this check
    exists for — everything else it reports is a declaration-time shape error
    that is merely annoying, while this one is unrepairable, because ids are
    never rewritten."""
    orphaned = [v for v in _run("C16", "fail") if v.artifact == "SHIP"]
    assert orphaned, "an id in an undeclared segment must be reported"
    assert "permanently carry it" in orphaned[0].message
    assert "closed: true" in orphaned[0].suggestion, (
        "the reader must be told the supported way to retire a segment")


def test_c16_says_why_a_legal_looking_name_is_refused():
    """`CART` is refused because the sequence alphabet can spell it, which is
    invisible unless the message says so — and the name can never be adopted
    later, so a reader owed an explanation gets it once."""
    refused = [v for v in _run("C16", "fail") if v.artifact == "CART"]
    assert refused and "alphabet" in refused[0].suggestion
    assert "AUTH" in refused[0].suggestion, "name a legal alternative, not just the rule"


def test_c16_ignores_drafts_and_unsegmented_ids():
    """Drafts carry ULIDs and constitutional RUs carry no segment: neither is a
    missing declaration, and reporting either would make the unsegmented form —
    which the design requires — look like an error. Assert the property on the
    id populations, not the store's cleanliness: a clean store proves this only
    by coincidence."""
    from rqunit.checks.c16 import _in_use

    store = Store.load(FIXTURES / "C16" / "pass")
    populations = {ru.id for ru in store.rus()}
    assert any(i.startswith("RU-draft-") for i in populations), "no draft to ignore"
    assert "RU-0001" in populations, "no unsegmented id to ignore"

    carried = _in_use(store)
    assert all(segment and segment.isupper() for segment in carried), carried
    assert not any(i.startswith("RU-draft-") or i == "RU-0001"
                   for members in carried.values() for i in members)


def test_c16_reports_the_unrepairable_violation_first():
    """Everything else C16 says is a typo in a file being edited right now.
    This one says ids exist naming a domain the store no longer declares, and
    ids are never rewritten — under four shape errors, nobody reads it."""
    violations = _run("C16", "fail")
    assert "permanently carry it" in violations[0].message


def test_c16_does_not_cry_permanence_over_a_mis_indented_entry(tmp_path):
    """A bare `- SHIP` is the wrong shape, not a store that stopped declaring
    SHIP. Reporting the mass-supersession violation on top of it would tell a
    consumer who mis-indented one line that they had committed the one edit
    that cannot be undone."""
    import shutil
    root = tmp_path / "store"
    shutil.copytree(FIXTURES / "C16" / "fail", root)
    (root / "spec" / "framework" / "segments.yaml").write_text("segments:\n  - SHIP\n")
    messages = [v.message for v in run_checks(Store.load(root), only="C16")]
    assert any("not a table" in m for m in messages)
    assert not any("permanently carry it" in m for m in messages)


def test_c16_missing_domain_is_survivable():
    """Nothing reads `domain`, and `domain: TBD` satisfies everything a machine
    can check of it. An error here is a red build for a sentence of prose."""
    domain = [v for v in _run("C16", "fail") if "domain" in v.message]
    assert domain and all(v.severity == "warning" for v in domain)


def test_c16_treats_a_closed_segment_as_declared():
    """Closing is the retirement path; its ids keep working forever. If closing
    read as removal the check would push consumers toward deleting the entry,
    which is the one edit that cannot be undone."""
    from rqunit.segments import declared, open_segments
    root = FIXTURES / "C16" / "pass"
    assert "BILL" in declared(root)
    assert "BILL" not in open_segments(root)
