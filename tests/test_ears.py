"""TASK-011 acceptance: golden-file suite is the parser contract. Expected
mappings assert selectively — only the keys each case lists."""

from pathlib import Path

import pytest
import yaml

from rqunit.parser.ears import EarsParseError, parse

GOLDEN = yaml.safe_load(
    (Path(__file__).parent.parent / "fixtures" / "parser" / "ears_golden.yaml").read_text()
)


def test_suite_meets_minimum_coverage():
    assert len(GOLDEN["parsed"]) >= 40
    assert len(GOLDEN["diagnosed"]) >= 10
    templates = {c["expected"]["template"] for c in GOLDEN["parsed"] if "template" in c["expected"]}
    assert {"ubiquitous", "event", "state", "unwanted", "optional", "gherkin"} <= templates


@pytest.mark.parametrize(
    "case", GOLDEN["parsed"], ids=[c["statement"][:56].strip() for c in GOLDEN["parsed"]]
)
def test_golden_parse(case):
    ast = parse(case["statement"], syntax=case.get("syntax", "ears"))
    for key, expected in case["expected"].items():
        actual = getattr(ast, key)
        if key == "bound":
            actual = {"text": actual.text, "kind": actual.kind} if actual else None
        assert actual == expected, f"slot {key!r}: {actual!r} != {expected!r}"


@pytest.mark.parametrize(
    "case", GOLDEN["diagnosed"], ids=[c["statement"][:56].strip() for c in GOLDEN["diagnosed"]]
)
def test_golden_diagnosis(case):
    with pytest.raises(EarsParseError) as exc:
        parse(case["statement"], syntax=case.get("syntax", "ears"))
    d = exc.value.diagnosis
    assert d.nearest_template == case["expected"]["nearest_template"]
    assert d.failed_slot == case["expected"]["failed_slot"]
    assert d.message  # every diagnosis carries an actionable message
