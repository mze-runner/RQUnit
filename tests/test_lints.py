"""Per-lint fixture harness (TASK-012…029 acceptance): every lint has a pass
store with zero violations of its rule and a fail store with at least two,
plus targeted message-quality assertions. The G1 criterion — the valid store
is clean under the FULL lint suite — is asserted here too."""

from pathlib import Path

import pytest

from rqunit.errors import StoreError
from rqunit.lints.base import discover, run_lints
from rqunit.store import Store

FIXTURES = Path(__file__).parent.parent / "fixtures"
LINTS = ["L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8", "L9",
         "L10", "L11", "L12", "L13", "L15", "L16", "L17", "L18",
         "L19", "L20", "L21", "L22", "L24"]
# L23 is deliberately absent and never to be issued: the shape-reference case it
# was reserved for is already L15's ("every manifest reference resolves"), and a
# field of a declared census IS a manifest reference. L15 carries the sharper
# message instead. Numbers are permanent, so an unused one stays unused.


def _load(root: Path) -> Store:
    """Full load, or a skeleton store when the fixture is deliberately
    schema-invalid (L8's fail store) — raw-file lints still operate."""
    try:
        return Store.load(root)
    except StoreError:
        return Store.load(root, changed=[])


def _dir(code: str, kind: str) -> Path:
    return FIXTURES / "lints" / f"L{int(code[1:]):02d}" / kind


def _run(code: str, kind: str):
    store = _load(_dir(code, kind))
    return [v for v in run_lints(store, only=code) if v.rule == code]


def test_registry_covers_exactly_the_built_lints():
    assert sorted(discover()) == sorted(LINTS)  # L14 deliberately absent until Phase 7 (plan D-P1.3)


@pytest.mark.parametrize("code", LINTS)
def test_lint_fixture_dirs_exist(code):
    assert _dir(code, "pass").is_dir() and _dir(code, "fail").is_dir()


@pytest.mark.parametrize("code", LINTS)
def test_pass_store_is_clean(code):
    assert _run(code, "pass") == []


@pytest.mark.parametrize("code", LINTS)
def test_fail_store_is_red(code):
    violations = _run(code, "fail")
    # Store-wide lints (L13) aggregate into a single violation by design.
    minimum = 1 if code == "L13" else 2
    assert len(violations) >= minimum, [v.message for v in violations]
    for v in violations:
        assert v.message and v.suggestion  # actionable, per common acceptance


def test_g1_valid_store_clean_under_full_suite():
    violations = run_lints(Store.load(FIXTURES / "store" / "valid"))
    assert violations == [], [f"{v.rule}: {v.artifact}: {v.message}" for v in violations]


def test_l2_scans_prose_never_token_interiors():
    # GAP17 regression (v0.10.4, same family as the GAP08 hyphen grammar):
    # the PASS store references {problem:too-many-requests} — 'many' inside a
    # token span must not trip; the FAIL store writes the identifier as bare
    # prose, which STILL trips (naming a fact in prose is restatement, and
    # a general hyphen exemption would hide real vagueness).
    assert any(v.artifact == "RU-0003" and "'many'" in v.message
               for v in _run("L2", "fail"))


def test_l20_is_finding_class_never_a_red_build():
    assert all(v.severity == "finding" for v in _run("L20", "fail"))


def test_l21_active_warns_draft_errors():
    severities = {v.severity for v in _run("L21", "fail")}
    assert severities == {"warning", "error"}
    draft_error = next(v for v in _run("L21", "fail") if v.severity == "error")
    assert "test" in draft_error.message and "contract" in draft_error.message  # missing type named


def test_l22_names_both_sides_of_the_contradiction():
    violations = _run("L22", "fail")
    assert any("RU-0001" in v.message for v in violations)          # direct RU link case
    assert any("RU-0002" in v.message for v in violations)          # done FEAT member case


# ------------------------------------------------------------ message quality

def test_l12_alias_hit_names_the_canonical_rename():
    v = next(x for x in _run("L12", "fail") if "alias" in x.message)
    assert "operations-manager" in v.suggestion


def test_l17_hits_carry_the_reference_suggestion():
    suggestions = {v.suggestion for v in _run("L17", "fail")}
    assert any("{value:retention.decision_log_days}" in s for s in suggestions)
    assert any("{message:order_cancelled}" in s for s in suggestions)


def test_l13_violation_lists_every_member():
    (v,) = _run("L13", "fail")
    assert v.message.count("RU-") == 16


def test_l1_diagnosis_names_the_nearest_template():
    assert all("nearest template" in v.suggestion for v in _run("L1", "fail"))


def test_l15_qualified_miss_says_no_fallback():
    v = next(x for x in _run("L15", "fail") if "service-billing/cancel_order" in x.message)
    assert "never fall back" in v.message


def test_l24_is_finding_class_only():
    """Two numbers can coincide innocently, so the tool reports and a human
    judges. Erroring on a guess teaches people to bypass the gate."""
    violations = _run("L24", "fail")
    assert violations and all(v.severity == "finding" for v in violations)
    assert all("{value:" in v.suggestion for v in violations)


def test_l24_leaves_referenced_bounds_and_unregistered_literals_alone():
    assert _run("L24", "pass") == []


def test_l15_diagnoses_an_unresolved_shape_reference_specifically():
    """L15 owns 'every manifest reference resolves'; a census field IS one. The
    shape case needs a sharper message, not a second rule number."""
    from rqunit.lints.l15 import _shape_diagnosis
    from rqunit.parser.tokens import parse_one

    message, suggestion = _shape_diagnosis(parse_one("{endpoint:get_order.outbound.ghost}"))
    assert "declares no field 'ghost'" in message and "§5.9" in suggestion
    message, _ = _shape_diagnosis(parse_one("{endpoint:get_order.inbound}"))
    assert "declares no `inbound`" in message
    assert _shape_diagnosis(parse_one("{endpoint:get_order}")) is None
    assert _shape_diagnosis(parse_one("{problem:conflict}")) is None
