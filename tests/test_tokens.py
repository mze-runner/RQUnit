"""TASK-010 acceptance: the fixture table drives the tokenizer contract."""

from pathlib import Path

import pytest
import yaml

from rqunit.parser.tokens import extract

FIXTURE = Path(__file__).parent.parent / "fixtures" / "parser" / "tokens.yaml"
CASES = yaml.safe_load(FIXTURE.read_text())["cases"]


def test_fixture_table_meets_minimum_coverage():
    assert len(CASES) >= 24
    malformed = [c for c in CASES if c.get("errors")]
    assert len(malformed) >= 8


@pytest.mark.parametrize("case", CASES, ids=[c["text"][:48] for c in CASES])
def test_tokenizer_case(case):
    tokens, errors = extract(case["text"])
    expected_tokens = case.get("tokens", [])
    expected_errors = case.get("errors", [])
    assert [
        {"kind": t.kind, "key": t.key, **({"qualifier": t.qualifier} if t.qualifier else {})}
        for t in tokens
    ] == expected_tokens
    assert [{"reason": e.reason} for e in errors] == expected_errors


def test_token_spans_point_into_the_text():
    text = "a {endpoint:healthz} b {value:x.y} c"
    tokens, errors = extract(text)
    assert not errors
    for t in tokens:
        assert text[t.start:t.start + len(t.raw)] == t.raw


def test_artifact_tokens_address_an_artifact_or_one_of_its_claims():
    """Two segments at most — an artifact is a flat claim set, not a nested
    payload, so there is nothing deeper to address."""
    from rqunit.parser.tokens import extract

    for raw in ("{artifact:jwt-access-token}", "{artifact:jwt-access-token.iss}",
                "{artifact:shared/jwt-access-token.sub}"):
        tokens, errors = extract(raw)
        assert not errors and tokens[0].kind == "artifact", raw
    for raw in ("{artifact:JWT}", "{artifact:a.b.c}"):
        _, errors = extract(raw)
        assert errors, raw
