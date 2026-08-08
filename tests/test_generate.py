"""Generation acceptance: deterministic rendering, the staleness/hand-edit
guard, statechart enumeration, and the advisory literal scan.

Everything here runs against FIXTURE stores. The product repository contains
no requirement store of its own — a store belongs to a consumer — so a test
that needed one to pass would be testing somebody else's data."""

import shutil
from pathlib import Path

from rqunit.generate import (
    check_current,
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


def test_every_plan_check_lands_in_its_models_suite_ignored():
    """Rendering semantics bind the adapter (its cargo tests own the deep
    assertions); what CORE must guarantee is that each model's staged suite
    carries exactly that model's checks and nothing runnable before a shim
    exists, and that the trace map covers the union — the property per model,
    never a one-model census the fixture's growth would break."""
    import json

    from rqunit.generate import plan_model_suite

    store = Store.load(VALID)
    staged = targets(store, VALID)
    all_planned: set[str] = set()
    for model_id in store.models():
        plan = plan_model_suite(store, model_id)
        stem = f"generated_mdl_{model_id.replace('-', '_')}"
        suite = next(content for path, content in staged.items()
                     if path.stem == stem)
        assert suite.count("#[test]") == len(plan["checks"])
        for check in plan["checks"]:
            assert f"fn {check['id']}()" in suite
        assert suite.count('#[ignore = "statechart shim pending') == suite.count("#[test]")
        all_planned |= {c["id"] for c in plan["checks"]}
    trace_map = json.loads(staged[VALID / "spec" / "projections" / "trace-map.json"])
    assert {key.rsplit("::", 1)[1] for key in trace_map["checks"]} == all_planned


def test_literal_scan_is_advisory_and_word_bounded():
    findings = scan_literals(Store.load(VALID), VALID)
    assert isinstance(findings, list)      # advisory: content varies per consumer
    for finding in findings:
        assert "import the generated constant" in finding


def test_a_store_with_no_stack_gets_no_crate_artifacts(tmp_path):
    """`conformance_crate` has a default so the path is knowable, but a default
    is not a declaration. Emitting a Rust crate into a repository that declared
    no Rust stack invents a build target nothing builds — and then fails the
    currency gate for not having it."""
    from click.testing import CliRunner

    from rqunit.cli.init import main as init_main

    CliRunner().invoke(init_main, ["--store", str(tmp_path)])
    produced = targets(Store.load(tmp_path), tmp_path)
    assert produced, "nothing generated at all — this test would pass vacuously"
    assert all("spec/projections" in str(p) for p in produced), (
        f"crate artifacts emitted with no stack declared: {sorted(map(str, produced))}")
    assert not (tmp_path / "spec-conformance-tests").exists()


def test_currency_problems_say_how_to_fix_themselves(tmp_path):
    """Hard rule: a violation the reader has to research is a failure of the
    rule. `missing` is the state every store is in before it first generates,
    so a bare path with no verb is the worst possible first contact."""
    root = tmp_path / "store"
    shutil.copytree(VALID, root)
    store = Store.load(root)
    write_all(store, root)

    generated = next(iter(targets(store, root)))
    generated.unlink()
    missing = check_current(store, root)
    assert missing and "rqunit generate all" in missing[0] and "§5.6" in missing[0]
    assert str(root) not in missing[0], "path should be store-relative, not absolute"

    write_all(store, root)
    generated.write_text(generated.read_text() + "\n// hand edit\n")
    stale = check_current(store, root)
    assert stale and "rqunit generate all" in stale[0] and "§5.6" in stale[0]


def test_literal_scan_serves_every_declared_stack_not_just_rust(tmp_path):
    """The advisory used to hardcode `stack("rust")` and glob `*.rs`, so a
    Node or JVM consumer got silence rather than findings. `literal_scan` now
    names FILES: the consumer's glob carries the only language-specific fact,
    leaving core a word-boundary numeric match that knows no language."""
    root = tmp_path / "store"
    shutil.copytree(VALID, root)
    (root / "rqunit.toml").write_text(
        '[stacks.node]\nliteral_scan = ["**/__tests__/*.js"]\n'
        '[stacks.jvm]\nliteral_scan = ["src/test/java/**/*.java"]\n')
    (root / "__tests__").mkdir()
    (root / "__tests__" / "a.test.js").write_text("expect(x).toBe(90);\n")
    java = root / "src" / "test" / "java" / "com"
    java.mkdir(parents=True)
    (java / "T.java").write_text("assertEquals(90, x);\n")

    findings = scan_literals(Store.load(root), root)
    assert any("a.test.js" in f for f in findings), findings
    assert any("T.java" in f for f in findings), findings


def test_literal_scan_survives_a_glob_that_catches_a_binary(tmp_path):
    """A consumer's glob is theirs to narrow; an unreadable file must not
    take the advisory down with it."""
    root = tmp_path / "store"
    shutil.copytree(VALID, root)
    (root / "rqunit.toml").write_text('[stacks.node]\nliteral_scan = ["blobs/*"]\n')
    (root / "blobs").mkdir()
    (root / "blobs" / "x.bin").write_bytes(b"\x00\x81\xfe binary 90 \x00")
    (root / "blobs" / "y.js").write_text("expect(x).toBe(90);\n")

    findings = scan_literals(Store.load(root), root)
    assert any("y.js" in f for f in findings)


def test_the_index_carries_the_segment_derived_from_the_id(tmp_path):
    """The index is the query surface — the handbook tells readers never to
    grep `spec/ru/` — and it already answers the capability and deployable
    axes. The domain axis has to be answerable in the same place, or segments
    are an organising idea nothing can query."""
    import json
    import shutil

    import yaml
    root = tmp_path / "store"
    shutil.copytree(VALID, root)
    source = root / "spec" / "ru" / "RU-0142.yaml"
    data = yaml.safe_load(source.read_text())
    data["id"] = "RU-ORD-0142"
    (root / "spec" / "ru" / "RU-ORD-0142.yaml").write_text(yaml.safe_dump(data, sort_keys=False))
    source.unlink()

    store = Store.load(root)
    index = json.loads(targets(store, root)[root / "spec" / "projections" / "ru-index.json"])
    by_id = {r["id"]: r for r in index["rus"]}
    assert by_id["RU-ORD-0142"]["segment"] == "ORD"
    assert all(r["segment"] is None for i, r in by_id.items() if i != "RU-ORD-0142")


def test_the_index_never_stores_a_second_copy_of_the_segment(tmp_path):
    """Derived, not stored: after activation the id is the only copy of that
    fact, and the draft's field is consumed precisely so a second copy cannot
    disagree with it."""
    import json
    import shutil
    root = tmp_path / "store"
    shutil.copytree(VALID, root)
    store = Store.load(root)
    index = json.loads(targets(store, root)[root / "spec" / "projections" / "ru-index.json"])
    assert all("segment" not in ru.raw for ru in store.rus())
    assert all("segment" in record for record in index["rus"])
