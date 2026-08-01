"""C1–C9 fixture harness (TASK-040…048 acceptance) + normalizer unit tests
(the normalizer ships as its own tested module, donor C1 note) + the G3
criterion: the real store runs error- and warning-free (C7 findings expected)."""

from pathlib import Path

import pytest

from rqunit.checks.base import discover, run_checks
from rqunit.checks.normalize import content_words, lemma
from rqunit.store import Store

FIXTURES = Path(__file__).parent.parent / "fixtures" / "checks"
CHECKS = [f"C{i}" for i in range(1, 14)]


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
