"""`rqunit lineage` — on-demand per-FEAT timeline. Invariants: read-only (no
files written), sittings grouped from gate stamps, Gate 2 records dated into
the timeline, GAPs and supersession links surfaced, RU argument resolves to
its feature, unknown ids are tool errors (exit 2)."""

import textwrap
from pathlib import Path

from click.testing import CliRunner

from rqunit.cli.lineage import main


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content))


def _store(tmp_path: Path) -> Path:
    root = tmp_path / "store"
    _write(root / "spec" / "intent" / "INT-0001.md", "Retain logs.\n")
    _write(root / "spec" / "features" / "FEAT-orders.yaml", """\
        id: FEAT-orders
        goal: Decision logs survive the audit window.
        source_ref: INT-0001#L1
        status: active
    """)
    _write(root / "spec" / "ru" / "RU-0100.yaml", """\
        id: RU-0100
        statement: The system shall retain decision logs for the audit window.
        syntax: ears
        status: superseded
        source_ref: INT-0001#L1
        feature: FEAT-orders
        verification:
        - { type: test, ref: "service-orders::shapes::base" }
        scope: { owns: [service-orders/fulfilment] }
        tags: [orders]
        gate1_stamp:
          hash: sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
          by: fixture-op
          at: '2026-07-20T10:00:00+00:00'
    """)
    _write(root / "spec" / "ru" / "RU-0101.yaml", """\
        id: RU-0101
        statement: The system shall retain decision logs for the extended audit window.
        syntax: ears
        status: active
        source_ref: INT-0001#L1
        feature: FEAT-orders
        supersedes: RU-0100
        verification:
        - { type: test, ref: "service-orders::shapes::base" }
        scope: { owns: [service-orders/fulfilment] }
        tags: [orders]
        gate1_stamp:
          hash: sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
          by: fixture-op
          at: '2026-07-22T10:00:00+00:00'
    """)
    _write(root / "spec" / "gaps" / "GAP-01J3F8KQZ2ABCDEFGHJKMNPQRS.yaml", """\
        id: GAP-01J3F8KQZ2ABCDEFGHJKMNPQRS
        question: "Which audit window applies after a dispute reopens?"
        severity: blocking
        raised_by: analyst
        affected: [RU-0101]
        status: resolved
        resolution: { int_ref: "INT-0001#L1", summary: "Extended window ruled." }
    """)
    _write(root / "spec" / "reviews" / "RU-0101" / "20260723T090000Z-window.yaml", """\
        ru: RU-0101
        criterion: "Is the extended window comprehensible?"
        verdict: pass
        reviewer: fixture-op
        at: '2026-07-23T09:00:00+00:00'
    """)
    return root


def test_feat_lineage_renders_all_sections_in_time_order(tmp_path):
    root = _store(tmp_path)
    before = sorted(p for p in root.rglob("*") if p.is_file())
    result = CliRunner().invoke(main, ["FEAT-orders", "--store", str(root)])
    assert result.exit_code == 0, result.output
    out = result.output
    assert "FEAT-orders — Decision logs survive the audit window." in out
    assert "INT-0001" in out
    assert "Gate 1 (fixture-op): activated RU-0100" in out
    assert "activated RU-0101 (supersedes RU-0100)" in out
    assert 'Gate 2 (fixture-op): pass — RU-0101' in out
    assert "GAP-01J3F8KQZ2ABCDEFGHJKMNPQRS (blocking, resolved → INT-0001#L1)" in out
    assert "RU-0100 superseded" in out and "superseded by RU-0101" in out
    # chronological: RU-0100's sitting, then RU-0101's, then the Gate 2 record
    assert out.index("2026-07-20") < out.index("2026-07-22") < out.index("2026-07-23")
    # a query verb writes nothing
    assert sorted(p for p in root.rglob("*") if p.is_file()) == before


def test_ru_argument_resolves_to_its_feature(tmp_path):
    result = CliRunner().invoke(main, ["RU-0101", "--store", str(_store(tmp_path))])
    assert result.exit_code == 0, result.output
    assert "FEAT-orders" in result.output


def test_unknown_ids_are_tool_errors(tmp_path):
    root = _store(tmp_path)
    assert CliRunner().invoke(main, ["FEAT-ghost", "--store", str(root)]).exit_code == 2
    assert CliRunner().invoke(main, ["RU-9999", "--store", str(root)]).exit_code == 2
