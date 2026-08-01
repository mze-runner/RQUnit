"""`rqunit` — the Requirement Unit Framework umbrella CLI.

One binary, noun–verb grammar, organized by lifecycle stage. Every verb
delegates to the implementation module of the same name.

Lifecycle map:
  adoption       rqunit init
  verification   rqunit lint · rqunit check · rqunit trace · rqunit conformance
  health         rqunit doctor
  reporting      rqunit report
  Gate 1         rqunit activate batch|restamp|reaffirm|resolve
  Gate 2         rqunit review record|guard
  governance     rqunit impact
  context        rqunit assemble build|disarm
  history        rqunit lineage
  projections    rqunit generate all|check|scan-literals · rqunit index
  enforcement    rqunit hooks h1|h2

Planned product verbs (not yet built — see the product backlog):
  rqunit intent capture · rqunit draft new · rqunit supersede · rqunit gap new
  · rqunit show · rqunit status · rqunit migrate · rqunit pack upgrade
"""

import click

from .activate import main as _activate
from .assemble import main as _assemble
from .check import main as _check
from .conformance import main as _conformance
from .doctor import main as _doctor
from .generate import main as _generate
from .hooks import main as _hooks
from .impact import main as _impact
from .index import main as _index
from .init import main as _init
from .lineage import main as _lineage
from .lint import main as _lint
from .report import main as _report
from .review import main as _review
from .trace import main as _trace


@click.group()
def main() -> None:
    """RQUnit — Requirement Unit Framework: manage the requirements lifecycle
    (store verification, gates, packets, projections, enforcement)."""


main.add_command(_init, name="init")
main.add_command(_lint, name="lint")
main.add_command(_check, name="check")
main.add_command(_trace, name="trace")
main.add_command(_conformance, name="conformance")
main.add_command(_doctor, name="doctor")
main.add_command(_report, name="report")
main.add_command(_activate, name="activate")
main.add_command(_review, name="review")
main.add_command(_impact, name="impact")
main.add_command(_assemble, name="assemble")
main.add_command(_lineage, name="lineage")
main.add_command(_generate, name="generate")
main.add_command(_index, name="index")
main.add_command(_hooks, name="hooks")
