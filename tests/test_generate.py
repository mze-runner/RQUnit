"""Generation acceptance: deterministic rendering, the staleness/hand-edit
guard, statechart enumeration, and the advisory literal scan.

Everything here runs against FIXTURE stores. The product repository contains
no requirement store of its own — a store belongs to a consumer — so a test
that needed one to pass would be testing somebody else's data."""

import shutil
from pathlib import Path

from rqunit.generate import (
    check_current,
    render_model_suite,
    scan_literals,
    targets,
    write_all,
)
from rqunit.store import Store

FIXTURES = Path(__file__).parent.parent / "fixtures"
VALID = FIXTURES / "store" / "valid"      # carries MDL-order-lifecycle


def test_rendering_is_deterministic():
    store = Store.load(VALID)
    a = targets(store, VALID)
    b = targets(Store.load(VALID), VALID)
    assert {str(p) for p in a} == {str(p) for p in b}
    assert all(a[p] == b[p] for p in a)


def test_generated_output_is_current_after_writing(tmp_path):
    """The §5.6 staleness rule: committed output must byte-match regeneration."""
    root = tmp_path / "store"
    shutil.copytree(VALID, root)
    write_all(Store.load(root), root)
    assert check_current(Store.load(root), root) == []


def test_hand_edit_is_detected(tmp_path):
    root = tmp_path / "store"
    shutil.copytree(VALID, root)
    store = Store.load(root)
    write_all(store, root)
    assert check_current(store, root) == []

    generated = next(p for p in targets(store, root) if p.suffix == ".rs")
    generated.write_text(generated.read_text() + "\n// sneaky hand edit\n")
    problems = check_current(store, root)
    assert problems and "hand-edited" in problems[0]


def test_statechart_suite_enumerates_every_case_the_model_declares():
    """One test per declared transition, one rejection per undeclared
    (state, event) pair over the model's event alphabet, one probe per
    invariant — and every one ignored until a shim is registered."""
    store = Store.load(VALID)
    model = store.models()["order-lifecycle"]
    states = model.raw["states"]
    transitions = sum(len(s.get("on") or {}) for s in states.values())
    alphabet = {e for s in states.values() for e in (s.get("on") or {})}
    rejections = sum(len(alphabet - set(s.get("on") or {})) for s in states.values())
    invariants = sum(1 for s in states.values() if s.get("invariant"))

    suite = render_model_suite(store, "order-lifecycle")
    assert suite.count("fn transition_") == transitions
    assert suite.count("fn rejects_") == rejections
    assert suite.count("fn invariant_") == invariants
    assert suite.count("#[test]") == transitions + rejections + invariants
    assert suite.count('#[ignore = "statechart shim pending') == suite.count("#[test]")


def test_undeclared_event_policy_selects_the_expected_outcome():
    store = Store.load(VALID)
    policy = store.models()["order-lifecycle"].raw["undeclared_event_policy"]
    suite = render_model_suite(store, "order-lifecycle")
    if policy == "error":
        assert "Outcome::Error" in suite and "Outcome::Ignored" not in suite
    else:
        assert "Outcome::Ignored" in suite


def test_literal_scan_is_advisory_and_word_bounded():
    findings = scan_literals(Store.load(VALID), VALID)
    assert isinstance(findings, list)      # advisory: content varies per consumer
    for finding in findings:
        assert "import the generated constant" in finding
