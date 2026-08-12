"""The demo store is gated, or it is decoration.

A showcase nothing runs is wrong within one revision, and a WRONG example is
worse than none: it teaches the previous vocabulary confidently. So the demo
lives in the suite, and it is also the only place the whole vocabulary is
exercised together — the fixture stores are deliberately minimal and
rule-scoped, so nothing else proves the pieces compose.
"""

import json
from pathlib import Path

from rqunit.checks.base import run_checks
from rqunit.conformance import load_actual, merge, reconcile, uncovered_families
from rqunit.lints.base import run_lints
from rqunit.store import Store

DEMO = Path(__file__).parent.parent / "demo" / "order-management"


def _store() -> Store:
    return Store.load(DEMO)


def test_demo_store_is_clean_under_lints_and_checks():
    """Nothing errors, and the only surviving warning is the one the demo
    exists to demonstrate: it ships no application, so its generated
    statechart suite cannot execute and contributes no mechanical depth.
    That warning was invisible until shim registration landed — L21 counted
    an unrunnable suite as depth — so its presence here is the framework
    telling the truth about a store it has always been telling it about."""
    violations = run_lints(_store()) + run_checks(_store())
    assert [v for v in violations if v.severity == "error"] == [], [
        f"{v.rule}: {v.artifact}: {v.message}" for v in violations if v.severity == "error"]
    warnings = [v for v in violations if v.severity == "warning"]
    assert all(v.rule == "L21" and "no registered shim" in v.message for v in warnings), [
        f"{v.rule}: {v.artifact}: {v.message}" for v in warnings]


def test_demo_reconciles_against_its_surface_artifact():
    artifact = load_actual(DEMO / "actual-surface.json")
    merged = merge([artifact])
    store = _store()
    divergences = [v for v in reconcile(store, merged) + uncovered_families(store, merged)
                   if v.severity == "error"]
    assert divergences == [], [f"{v.rule}: {v.message}" for v in divergences]


def test_the_demo_still_has_something_to_report():
    """Findings are the point, not a defect. A store with nothing to say
    teaches nothing about what the tool is for — so if these ever vanish it
    means the demo was tidied into a trophy."""
    findings = {v.rule for v in run_checks(_store()) if v.severity == "finding"}
    assert "C7" in findings and "C14" in findings


def test_the_demo_exercises_the_vocabulary_it_exists_to_show():
    """Invariants, not counts: each construct is PRESENT. Asserting how many
    would break on ordinary growth of the example."""
    store = _store()
    orders = store.manifests()["service-orders"].raw
    shared = store.manifests()["shared"].raw

    endpoint = next(e for e in orders["endpoints"] if e["id"] == "cancel_order")
    assert {"emits", "audits", "publishes"} <= set(endpoint)     # three side effects
    assert any(f.get("presence") == "forbidden"                  # mass-assignment boundary
               for f in endpoint["inbound"]["fields"])

    assert shared.get("artifacts"), "the encoding-boundary case"
    assert shared.get("audit_forbidden"), "store-wide negative claim"
    assert any(e.get("retention") for e in orders["audit_events"])
    assert any(m.get("audits") for m in orders["messages"]), "async handler records evidence"
    assert any(f.get("artifact")                                 # the edge to an artifact
               for e in orders["endpoints"]
               for f in (e.get("outbound") or {}).get("fields") or []
               if isinstance(f, dict))

    statements = " ".join(ru.raw["statement"] for ru in store.rus())
    assert "{artifact:" in statements and "{audit:" in statements
    assert ".inbound." in statements                             # a field addressed directly
