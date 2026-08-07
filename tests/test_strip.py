"""The off-ramp (`rqunit trace --strip`). Invariants: core alone decides which
tokens go, so orphan-only is the default and a link already re-pointed survives
a mid-migration run; a stripper that edits beyond its instruction is refused
rather than written; nothing reaches disk without --apply; and a stack that can
be adopted but not un-adopted says so instead of reporting a clean sweep."""

import json
import shutil
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from rqunit.cli.trace import main as trace_main
from rqunit.errors import BadConfig
from rqunit.store import Store
from rqunit.strip import apply, plan

FIXTURES = Path(__file__).parent.parent / "fixtures"
TRACED = FIXTURES / "store" / "traced"

# A stripper stub: echoes back one rewritten file and the checks it was asked
# about. Enough to exercise every judgment core makes about the answer.
STRIPPER = """
import json, sys
request = json.load(sys.stdin)
ids = [c["id"] for c in request["checks"]]
print(json.dumps({
    "contract_version": 1,
    "generated_by": "stub 0.1",
    "files": [{"path": %(path)r, "content": "rewritten\\n"}],
    "stripped": %(stripped)s,
}))
"""


SOURCE = "itest/tests/orders.rs"


def _store(tmp_path: Path) -> Path:
    """The traced fixture plus the two cases an off-ramp exists for: an
    annotation naming a retired RU, and one naming a retired RU BESIDE a live
    one. The shared fixture stays clean — it is the store other tests assert
    is green, and seeding orphans there would redden it for everyone."""
    root = tmp_path / "store"
    shutil.copytree(TRACED, root)
    observed = root / "scanned-checks.json"
    data = json.loads(observed.read_text())
    data["checks"] += [
        {"id": "itest::orders::orphan_only", "path": SOURCE,
         "fn": "orphan_only", "verifies": ["RU-9999"]},
        {"id": "itest::orders::mixed", "path": SOURCE,
         "fn": "mixed", "verifies": ["RU-0142", "RU-9999"]},
    ]
    observed.write_text(json.dumps(data, indent=2) + "\n")
    return root


def _wire_stripper(root: Path, body: str) -> None:
    script = root / "stripper.py"
    script.write_text(body)
    toml = root / "rqunit.toml"
    toml.write_text(toml.read_text()
                    + f'\nstripper = {{ cmd = ["{sys.executable}", "{script}"] }}\n')


def _stub(path: str = SOURCE, stripped: str = "ids") -> str:
    return STRIPPER % {"path": path, "stripped": stripped}


def test_only_orphans_go_by_default(tmp_path):
    """A strip run mid-migration must not destroy the links already
    re-pointed — which is the whole reason orphan-only is the default."""
    root = _store(tmp_path)
    _wire_stripper(root, _stub())
    decided = plan(Store.load(root), root)

    removed = {token for entries in decided.per_stack.values()
               for entry in entries for token in entry["remove"]}
    assert removed, "nothing was planned — this test would pass vacuously"
    active = {ru.id for ru in Store.load(root).rus() if ru.status == "active"}
    assert not (removed & active), f"an active RU's link was planned for removal: {removed}"
    assert "infrastructure" not in removed


def test_all_takes_everything_including_the_infrastructure_markers(tmp_path):
    """Off-boarding, not migration: `infrastructure` is the framework's
    vocabulary too, so leaving it behind would leave the codebase still
    speaking a language nothing reads."""
    root = _store(tmp_path)
    _wire_stripper(root, _stub())
    everything = plan(Store.load(root), root, everything=True)
    orphans_only = plan(Store.load(root), root)

    all_tokens = {t for e in everything.per_stack.values() for c in e for t in c["remove"]}
    assert "infrastructure" in all_tokens
    assert everything.total >= orphans_only.total
    assert all_tokens > {t for e in orphans_only.per_stack.values()
                         for c in e for t in c["remove"]}


def test_a_dry_run_writes_nothing(tmp_path):
    """This edits source the consumer owns. A destructive default is how a
    tool gets run once and then distrusted."""
    root = _store(tmp_path)
    _wire_stripper(root, _stub())
    target = root / SOURCE
    before = target.read_text()

    result = apply(root, plan(Store.load(root), root), write=False)
    assert result.written, "nothing reported — this test would pass vacuously"
    assert target.read_text() == before


def test_apply_writes_what_the_stripper_returned(tmp_path):
    root = _store(tmp_path)
    _wire_stripper(root, _stub())
    target = root / SOURCE

    apply(root, plan(Store.load(root), root), write=True)
    assert target.read_text() == "rewritten\n"


def test_a_stripper_reporting_checks_it_was_not_asked_about_is_refused(tmp_path):
    """The request is the complete instruction. An off-ramp that silently
    edits more than it was told to is worse than none."""
    root = _store(tmp_path)
    _wire_stripper(root, _stub(stripped='ids + ["someone-elses::check::id"]'))
    target = root / SOURCE
    before = target.read_text()

    with pytest.raises(BadConfig, match="not asked about"):
        apply(root, plan(Store.load(root), root), write=True)
    assert target.read_text() == before, "refused, but wrote anyway"


@pytest.mark.parametrize("escape", ["/etc/passwd", "../outside.rs"])
def test_a_path_escaping_the_root_is_refused(tmp_path, escape):
    root = _store(tmp_path)
    _wire_stripper(root, _stub(path=escape))
    with pytest.raises(BadConfig, match="escaping the consumer root"):
        apply(root, plan(Store.load(root), root), write=True)


def test_artifact_mode_cannot_serve_a_stripper(tmp_path):
    """A committed file cannot answer a request computed moments ago — it
    would be an earlier run's edits applied to current source."""
    root = _store(tmp_path)
    toml = root / "rqunit.toml"
    toml.write_text(toml.read_text() + '\nstripper = { artifact = "stripped.json" }\n')
    with pytest.raises(BadConfig, match="artifact mode cannot serve a stripper"):
        apply(root, plan(Store.load(root), root), write=True)


def test_a_stack_without_a_stripper_is_reported_not_skipped(tmp_path):
    """A stack adoptable but not un-adoptable is a one-way door, and the
    operator has to see that before believing a clean sweep."""
    root = _store(tmp_path)                       # traced fixture declares none
    decided = plan(Store.load(root), root)
    assert decided.unavailable == ["rust"]
    assert decided.total == 0

    result = CliRunner().invoke(trace_main, ["--store", str(root), "--strip"])
    assert result.exit_code == 0
    assert "declares no stripper role" in result.output


def test_all_and_apply_are_meaningless_without_strip(tmp_path):
    root = _store(tmp_path)
    for flag in ("--all", "--apply"):
        result = CliRunner().invoke(trace_main, ["--store", str(root), flag])
        assert result.exit_code == 2
        assert "without --strip" in result.output


def test_the_cli_says_nothing_was_written_when_nothing_was(tmp_path):
    root = _store(tmp_path)
    _wire_stripper(root, _stub())
    result = CliRunner().invoke(trace_main, ["--store", str(root), "--strip"])
    assert result.exit_code == 0
    assert "would rewrite" in result.output
    assert "--apply" in result.output
    assert json.loads((root / "scanned-checks.json").read_text())   # store untouched
