"""M3 — final states declare no transitions (spec §6.3). One of the statechart
dialect's beyond-schema graph facts: implemented once in model_rules, surfaced
here at lint and refused at generation with the same message."""

from ..model_rules import dialect_violations
from .base import lint


@lint("M3")
def run(store):
    return dialect_violations(store, only="M3")
