"""TASK-002 fixture suites: every file under fixtures/schemas/<kind>/pass
validates against its schema, every file under .../fail is rejected. These
EXTEND the reference-pack smoke cases (test_schema_smoke.py)."""

from pathlib import Path

import pytest
import yaml
from jsonschema import ValidationError

from rqunit.schemas import SCHEMA_FILES, validator

FIXTURES = Path(__file__).parent.parent / "fixtures" / "schemas"


def _cases(expected: str):
    out = []
    for kind in SCHEMA_FILES:
        for path in sorted((FIXTURES / kind / expected).glob("*.yaml")):
            out.append(pytest.param(kind, path, id=f"{kind}/{path.stem}"))
    return out


def test_every_schema_has_minimum_fixture_coverage():
    for kind in SCHEMA_FILES:
        assert len(list((FIXTURES / kind / "pass").glob("*.yaml"))) >= 3, kind
        assert len(list((FIXTURES / kind / "fail").glob("*.yaml"))) >= 5, kind


@pytest.mark.parametrize("kind,path", _cases("pass"))
def test_pass_fixture_validates(kind, path):
    with open(path) as f:
        instance = yaml.safe_load(f)
    validator(kind).validate(instance)


@pytest.mark.parametrize("kind,path", _cases("fail"))
def test_fail_fixture_is_rejected(kind, path):
    with open(path) as f:
        instance = yaml.safe_load(f)
    with pytest.raises(ValidationError):
        validator(kind).validate(instance)
