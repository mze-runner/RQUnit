"""EARS parser (TASK-011, formats §3). Classifies a statement into the five
templates (plus gherkin mode), extracting typed slots. The golden suite at
fixtures/parser/ears_golden.yaml is the executable contract — extend the suite
before extending the grammar.

Slot notes pinned by the golden suite:
- `subject` is the leading article-stripped ident of the trigger/condition;
  whether it IS an actor is L12's judgment (registry + hyphenation heuristic),
  not the parser's.
- `bound` is whatever follows " within " (up to a comma or the period);
  classification: literal (number+unit), ref ({value:...}), word (anything
  else — L2's vague-term candidate).
- `shall_clauses` counts coordinated shall-clauses for L3.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_SYSTEM = r"(?:[Tt]he system|[a-z][a-z0-9]*(?:-[a-z0-9]+)+)"

_TEMPLATES = {
    "event": re.compile(
        rf"^When (?P<clause>.+?), (?P<system>{_SYSTEM}) shall (?P<response>.+)\.$"
    ),
    "state": re.compile(
        rf"^While (?P<clause>.+?), (?P<system>{_SYSTEM}) shall (?P<response>.+)\.$"
    ),
    "unwanted": re.compile(
        rf"^If (?P<clause>.+?), then (?P<system>{_SYSTEM}) shall (?P<response>.+)\.$"
    ),
    "optional": re.compile(
        rf"^Where (?P<clause>.+?), (?P<system>{_SYSTEM}) shall (?P<response>.+)\.$"
    ),
    "ubiquitous": re.compile(
        rf"^(?P<system>{_SYSTEM}) shall (?P<response>.+)\.$"
    ),
}

_GHERKIN = re.compile(
    rf"^Given (?P<given>.+?), [Ww]hen (?P<clause>.+?), [Tt]hen (?P<system>{_SYSTEM}) "
    r"shall (?P<response>.+)\.$"
)

_KEYWORD_TO_TEMPLATE = [
    ("When ", "event"), ("While ", "state"), ("If ", "unwanted"),
    ("Where ", "optional"), ("Given ", "gherkin"),
]

_SUBJECT = re.compile(r"^(?:a |an |the )?(?P<subject>[a-z][a-z0-9-]*)\b")
_BOUND = re.compile(r" within (?P<bound>\{value:[^}]*\}(?: [a-z]+)?|[^,.]+?)(?=,|\.$|$)")
_LITERAL_BOUND = re.compile(r"^\d+(?:\.\d+)?\s*[a-zA-Z]+")


@dataclass(frozen=True)
class Bound:
    text: str
    kind: str  # literal | ref | word


@dataclass(frozen=True)
class Statement:
    template: str          # ubiquitous | event | state | unwanted | optional | gherkin
    system: str
    response: str
    clause: str | None = None    # trigger (event/gherkin), state-cond, condition, feature-cond
    given: str | None = None     # gherkin only
    subject: str | None = None   # leading ident of the clause (L12 candidate)
    negated: bool = False
    bound: Bound | None = None
    shall_clauses: int = 1


@dataclass(frozen=True)
class Diagnosis:
    nearest_template: str
    failed_slot: str
    message: str


class EarsParseError(Exception):
    def __init__(self, diagnosis: Diagnosis):
        self.diagnosis = diagnosis
        super().__init__(f"{diagnosis.nearest_template}/{diagnosis.failed_slot}: {diagnosis.message}")


def normalize(text: str) -> str:
    """YAML folded scalars arrive with soft newlines — collapse whitespace."""
    return " ".join(text.split())


def parse(text: str, syntax: str = "ears") -> Statement:
    s = normalize(text)
    if syntax == "gherkin":
        return _parse_gherkin(s)
    for keyword, template in _KEYWORD_TO_TEMPLATE:
        if s.startswith(keyword):
            if template == "gherkin":
                raise EarsParseError(Diagnosis(
                    "gherkin", "syntax",
                    "statement uses Given/When/Then but declares syntax: ears"))
            return _parse_template(template, s)
    return _parse_template("ubiquitous", s)


def _parse_template(template: str, s: str) -> Statement:
    m = _TEMPLATES[template].match(s)
    if not m:
        raise EarsParseError(_diagnose(template, s))
    clause = m.groupdict().get("clause")
    return _build(template, m.group("system"), m.group("response"), clause=clause)


def _parse_gherkin(s: str) -> Statement:
    m = _GHERKIN.match(s)
    if not m:
        raise EarsParseError(_diagnose("gherkin", s))
    return _build("gherkin", m.group("system"), m.group("response"),
                  clause=m.group("clause"), given=m.group("given"))


def _build(template: str, system: str, response: str,
           clause: str | None = None, given: str | None = None) -> Statement:
    subject = None
    if clause:
        sm = _SUBJECT.match(clause)
        subject = sm.group("subject") if sm else None
    bound = None
    bm = _BOUND.search(response + ".")
    if bm:
        text = bm.group("bound").strip()
        if text.startswith("{value:"):
            kind = "ref"
        elif _LITERAL_BOUND.match(text):
            kind = "literal"
        else:
            kind = "word"
        bound = Bound(text=text, kind=kind)
    return Statement(
        template=template,
        system=system,
        response=response,
        clause=clause,
        given=given,
        subject=subject,
        negated=response.startswith("not "),
        bound=bound,
        shall_clauses=1 + response.count(" shall "),
    )


def _diagnose(template: str, s: str) -> Diagnosis:
    if not s.endswith("."):
        return Diagnosis(template, "terminator", "statement must end with a period")
    if " shall " not in s:
        return Diagnosis(template, "shall-clause",
                         "no ' shall ' clause — every statement carries exactly one normative verb")
    if template == "unwanted" and ", then " not in s:
        return Diagnosis(template, "separator",
                         "If-template requires ', then ' between condition and system clause")
    if template in ("event", "state", "optional", "gherkin") and ", " not in s:
        return Diagnosis(template, "separator",
                         f"{template}-template requires ', ' between its clause and the system clause")
    return Diagnosis(template, "system",
                     "the shall-clause subject must be 'the system' or a service name "
                     "(actors belong inside the trigger/condition, or as the response's object)")
