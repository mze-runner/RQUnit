"""Per-lint fixture harness (TASK-012…029 acceptance): every lint has a pass
store with zero violations of its rule and a fail store with at least two,
plus targeted message-quality assertions. The G1 criterion — the valid store
is clean under the FULL lint suite — is asserted here too."""

from pathlib import Path

import shutil

import pytest

from rqunit.errors import StoreError
from rqunit.lints.base import discover, run_lints
from rqunit.store import Store

FIXTURES = Path(__file__).parent.parent / "fixtures"
LINTS = ["L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8", "L9",
         "L10", "L11", "L12", "L13", "L15", "L16", "L17", "L18",
         "L19", "L20", "L21", "L22", "L24", "L25", "L26", "L27",
         # The statechart dialect family (§6.3): graph facts the schema cannot
         # express. M5 is deliberately absent — event vocabulary resolves
         # against manifests, which makes it C8's cross-artifact question.
         "M1", "M2", "M3", "M4", "M6"]
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
    name = f"L{int(code[1:]):02d}" if code.startswith("L") else code
    return FIXTURES / "lints" / name / kind


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
    # The message names what would satisfy the rule. Since v0.14 a security RU
    # must BIND a shape, not merely carry two verification types, so the naming
    # is of token forms rather than of missing types.
    assert "bind a declared shape" in draft_error.message
    assert "{audit:<code>}" in draft_error.message


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


def test_l21_binds_shape_reads_the_statement_not_the_verification_block():
    """Shape-binding moved: an RU used to prove it by carrying
    `verification: contract`, and now does so by addressing a field. Without
    this the policy could demand depth but not relevance."""
    from rqunit.lints.l21 import binds_shape

    store = Store.load(FIXTURES / "store" / "valid")
    ru = next(iter(store.rus()))

    def with_statement(text):
        # scope drives resolution: a constitutional RU has none, and would search
        # `shared` only. Give the clone a service so the tokens can land.
        raw = {**ru.raw, "statement": text, "scope": {"owns": ["service-orders/domain"]}}
        clone = type(ru)(path=ru.path, raw=raw, id=ru.id, status=ru.status, tier=ru.tier)
        return binds_shape(store, clone)

    # naming a surface is not describing what it carries
    assert not with_statement("When a user calls {endpoint:cancel_order}, the system shall halt.")
    # addressing a direction, or a field within it, is
    assert with_statement("The system shall not populate {endpoint:cancel_order.inbound.reason}.")
    assert with_statement("The system shall record {audit:orders.cancelled}.")
    # an unresolved ref is L15's business, not this rule's
    assert not with_statement("The system shall record {audit:no.such.code}.")


def test_l21_shape_requirement_names_the_forms_that_satisfy_it():
    from rqunit.lints.l21 import violation_reason

    rule = {"require": {"binds_shape": True}}
    assert violation_reason(rule, [{"type": "test", "ref": "x"}], shape_bound=True) is None
    reason = violation_reason(rule, [{"type": "test", "ref": "x"}], shape_bound=False)
    assert "{endpoint:<id>.<direction>" in reason and "{audit:<code>}" in reason


def test_l25_catches_a_subject_naming_nothing():
    """The EARS parser admits `the system` or any hyphenated lowercase word, by
    shape alone — so a typo in the subject was silent until now."""
    violations = _run("L25", "fail")
    typo = next(v for v in violations if v.artifact == "RU-0001")
    assert "has no manifest" in typo.message and "typo" in typo.suggestion


def test_l25_catches_the_misfiled_ru():
    """Two claims about which service governs an RU — the subject and
    scope.owns — coexisted with nothing reconciling them. §5.3 forbade this
    already; it had no teeth."""
    misfiled = next(v for v in _run("L25", "fail") if v.artifact == "RU-0002")
    assert "does not govern" in misfiled.message
    assert "read coupling, not governance" in misfiled.suggestion


def test_l25_leaves_the_system_alone():
    """`the system` claims no service, which is what makes the distinction
    between store-wide and service-scoped behaviour mean anything."""
    assert _run("L25", "pass") == []


def test_l17_scans_prose_never_token_interiors(tmp_path):
    """Regression, end to end: L17 read the RAW statement, so an RU that
    referenced a fact CORRECTLY was told to reference it. An audit code and a
    message subject sharing a string is ordinary, and the demo store surfaced
    it. L2 got this fix in v0.10.4; L17 did not."""
    root = tmp_path / "store"
    shutil.copytree(FIXTURES / "store" / "valid", root)
    ru = root / "spec" / "ru" / "RU-0142.yaml"
    ru.write_text(
        "id: RU-0142\n"
        "statement: >\n"
        "  The system shall record {audit:orders.cancelled} for every cancellation.\n"
        "syntax: ears\nstatus: active\nsource_ref: INT-0057#L1-2\n"
        "verification:\n  - { type: test, ref: TODO(pending) }\n"
        "scope:\n  owns: [service-orders/fulfilment]\ntags: [orders]\n")
    hits = [v for v in run_lints(Store.load(root), only="L17")
            if v.rule == "L17" and v.artifact == "RU-0142"]
    assert hits == [], [h.message for h in hits]

    # a BARE identifier in prose is still restatement, and still caught
    ru.write_text(ru.read_text().replace(
        "record {audit:orders.cancelled} for", "publish orders.cancelled for"))
    assert [v for v in run_lints(Store.load(root), only="L17")
            if v.rule == "L17" and v.artifact == "RU-0142"]


# ------------------------------------------------------------ M dialect family

def test_m_rules_refuse_generation_with_the_same_messages(tmp_path):
    """One implementation, two surfaces: a model whose violation would make
    the RENDERED SUITE wrong must not render — an M2 violation used to emit a
    test asserting a transition to a state that does not exist, failing only
    at shim runtime. The refusal names the model file, per hard rule 6."""
    from rqunit.errors import DialectViolation
    from rqunit.generate import plan_model_suite

    root = tmp_path / "store"
    shutil.copytree(_dir("M2", "fail"), root)
    store = _load(root)
    model_id = next(iter(store.models()))
    with pytest.raises(DialectViolation) as caught:
        plan_model_suite(store, model_id)
    message = str(caught.value)
    assert "[M2]" in message and "not a declared state" in message and "§6.3" in message
    assert "spec/models/" in message


def test_rules_the_plan_never_reads_report_without_blocking(tmp_path):
    """M1 and M4 are modeling-quality judgments: the plan reads neither
    `initial` nor `type: final`, so gating rendering on them would block a
    consumer for a fact rendering never consults."""
    from rqunit.generate import plan_model_suite

    for code in ("M1", "M4"):
        root = tmp_path / code
        shutil.copytree(_dir(code, "fail"), root)
        store = _load(root)
        assert _run(code, "fail"), f"{code} must still be reported"
        for model_id in store.models():
            plan_model_suite(store, model_id)      # renders anyway


def test_a_model_violation_is_a_violation_on_every_surface(tmp_path):
    """`lint` and `generate check` must agree on the CATEGORY of the same
    fact: exit 1 (your model is wrong), never exit 2 (rqunit is broken)."""
    from click.testing import CliRunner

    from rqunit.cli.generate import main as generate_main

    root = tmp_path / "store"
    shutil.copytree(FIXTURES / "store" / "valid", root)
    model = root / "spec" / "models" / "MDL-order-lifecycle.statechart.json"
    raw = model.read_text().replace('"CANCEL": "cancelling"', '"CANCEL": "nowhere"')
    model.write_text(raw)
    result = CliRunner().invoke(generate_main, ["check", "--store", str(root)])
    assert result.exit_code == 1, result.output
    assert "[M2]" in result.output


def test_m4_does_not_cascade_when_m1_already_fired():
    """A walk with no lawful start would report one defect under two numbers;
    the M1 fail store must be red for M1's reason alone."""
    assert _run("M1", "fail") and _run("M4", "fail")     # both rules do fire on their own stores
    m1_store = _load(_dir("M1", "fail"))
    assert [v for v in run_lints(m1_store, only="M4") if v.rule == "M4"] == []


def test_m_rules_name_the_model_and_cite_the_section():
    for code in ("M1", "M2", "M3", "M4", "M6"):
        violations = _run(code, "fail")
        assert all(v.artifact.startswith("MDL-") and "§6.3" in v.suggestion
                   for v in violations)


def test_m4_is_visible_debt_not_a_block():
    """A cyclic lifecycle — a reopenable order, a subscription — legitimately
    declares no final state, and M3 forbids giving a final one a way out.
    Erroring on that would block an honest consumer at lint, at generation,
    and at every unrelated activation."""
    assert all(v.severity == "warning" for v in _run("M4", "fail"))
    for code in ("M1", "M2", "M3", "M6"):
        assert all(v.severity == "error" for v in _run(code, "fail"))


def test_l27_is_silent_in_a_store_that_never_adopted_segments(tmp_path):
    """Segments are optional and a store may legitimately never take them up.
    A rule that fires on a shape nobody opted into is not enforcing a decision,
    it is demanding one."""
    import shutil
    root = tmp_path / "store"
    shutil.copytree(FIXTURES / "lints" / "L27" / "fail", root)
    (root / "spec" / "framework" / "segments.yaml").unlink()
    assert [v for v in run_lints(Store.load(root)) if v.rule == "L27"] == []


def test_l27_leaves_permanent_ids_alone():
    """An active RU minted before its store adopted segments can never acquire
    one — ids are never rewritten. Reporting it would be a warning with no
    available fix, which is how a tool teaches people to ignore it."""
    store = Store.load(FIXTURES / "lints" / "L27" / "fail")
    flagged = {v.artifact for v in _run("L27", "fail")}
    actives = {ru.id for ru in store.rus() if ru.status != "draft"}
    assert actives, "no active RU in the fixture — this test would be vacuous"
    assert not (flagged & actives)


def test_l27_exempts_the_population_that_is_meant_to_be_unsegmented():
    """Unsegmented is a positive claim — 'this governs the store' — and the
    schema already makes that the constitutional tier by letting it omit
    `scope.owns` where every other tier must carry one."""
    store = Store.load(FIXTURES / "lints" / "L27" / "pass")
    tiers = {ru.raw.get("tier") for ru in store.rus() if ru.status == "draft"}
    assert "constitutional" in tiers, "no constitutional draft to exempt"
    assert _run("L27", "pass") == []


def test_l27_names_the_segments_the_store_actually_declares():
    """A suggestion telling someone to pick a segment without saying which ones
    exist sends them to a file to find out. Assert it against the registry, not
    against literals — the point is that the two agree."""
    import re

    from rqunit.segments import declared

    root = FIXTURES / "lints" / "L27" / "fail"
    for violation in _run("L27", "fail"):
        offered = set(re.findall(r"\b[A-Z][A-Z0-9]{1,7}\b", violation.suggestion))
        assert declared(root) <= offered, violation.suggestion


def test_l27_catches_the_mirror_mistake_too():
    """A constitutional draft carrying a segment is the same confusion inverted,
    and the more expensive one: the allocator honours the field regardless of
    tier, so it mints a permanent segmented id for a store-wide invariant."""
    import shutil

    import yaml
    root = FIXTURES / "lints" / "L27" / "pass"
    with __import__("tempfile").TemporaryDirectory() as tmp:
        copy = Path(tmp) / "store"
        shutil.copytree(root, copy)
        target = next(p for p in (copy / "spec" / "ru").glob("RU-draft-*.yaml")
                      if yaml.safe_load(p.read_text()).get("tier") == "constitutional")
        data = yaml.safe_load(target.read_text())
        data["segment"] = "ORD"
        target.write_text(yaml.safe_dump(data, sort_keys=False))

        flagged = [v for v in run_lints(Store.load(copy)) if v.rule == "L27"]
        assert flagged and "constitutional" in flagged[0].message
        assert "Drop `segment:`" in flagged[0].suggestion


def test_l27_survives_a_registry_it_cannot_parse(tmp_path):
    """L27 is the first lint to read segments.yaml, so letting a parse error
    escape would abandon the whole run — every other lint unreported — over one
    mis-indented line, under a message about a file nobody touched."""
    import shutil
    root = tmp_path / "store"
    shutil.copytree(FIXTURES / "lints" / "L27" / "fail", root)
    (root / "spec" / "framework" / "segments.yaml").write_text("segments:\n  - name: ORD\n   bad\n")

    violations = run_lints(Store.load(root))
    assert [v for v in violations if v.rule == "L27"] == []
    assert violations is not None      # the run completed rather than aborting
