"""ADR completion (spec §7.3, formats §10): rationale records live in-store at
spec/rationale/ADR-<slug>.md, resolve or fail L7, are byte-fingerprinted at
activation, flip dependents suspect on edit (L20), and render verbatim into
packet §3."""

import shutil
from pathlib import Path

import pytest

from rqunit.assemble import render_packet
from rqunit.canonical import expected_fingerprints, file_fingerprint, link_fingerprint
from rqunit.errors import UnknownArtifact
from rqunit.lints.base import run_lints
from rqunit.store import Store

FIXTURES = Path(__file__).parent.parent / "fixtures"
WITH_ADR = FIXTURES / "lints" / "L07" / "pass"     # RU-0102 → ADR-audit-window
DANGLING = FIXTURES / "lints" / "L07" / "fail"     # RU-0104 → ADR-ghost (absent)
STAMPED = FIXTURES / "lints" / "L20" / "pass"      # RU-0102 fingerprints the ADR
NOW = "2026-07-26T12:00:00+00:00"


# ------------------------------------------------------------ loader

def test_store_loads_rationale_dir():
    store = Store.load(WITH_ADR)
    assert list(store.adrs()) == ["ADR-audit-window"]
    assert store.adr_path("ADR-audit-window").is_file()
    assert store.adr_path("ADR-ghost") is None


def test_non_adr_filename_in_rationale_is_rejected(tmp_path):
    root = tmp_path / "store"
    shutil.copytree(WITH_ADR, root)
    (root / "spec" / "rationale" / "notes.md").write_text("stray prose\n")
    with pytest.raises(UnknownArtifact):
        Store.load(root)


# ------------------------------------------------------------ fingerprints

def test_adr_link_fingerprint_is_the_file_byte_hash():
    store = Store.load(WITH_ADR)
    path = store.adr_path("ADR-audit-window")
    assert link_fingerprint(store, "ADR-audit-window") == file_fingerprint(path)
    assert link_fingerprint(store, "ADR-ghost") is None


def test_expected_fingerprints_cover_rationale_ref():
    store = Store.load(WITH_ADR)
    ru = next(r for r in store.rus() if r.id == "RU-0102")
    fps = expected_fingerprints(store, ru.raw)
    assert "ADR-audit-window" in fps


def test_editing_a_referenced_adr_flips_the_dependent_suspect(tmp_path):
    root = tmp_path / "store"
    shutil.copytree(STAMPED, root)
    assert [v for v in run_lints(Store.load(root), only="L20") if v.rule == "L20"] == []
    adr = root / "spec" / "rationale" / "ADR-audit-window.md"
    adr.write_text(adr.read_text() + "\nRewritten rationale.\n")
    flagged = [v for v in run_lints(Store.load(root), only="L20") if v.rule == "L20"]
    assert any(v.artifact == "RU-0102" and "ADR-audit-window" in v.message for v in flagged)
    assert all(v.severity == "finding" for v in flagged)


# ------------------------------------------------------------ packet §3

def test_packet_renders_linked_adr_content():
    store = Store.load(WITH_ADR)
    packet = render_packet(store, WITH_ADR, "TASK-9998", ["RU-0102"], now=NOW)
    section = packet.split("# 3. Rationale")[1].split("# 4.")[0]
    assert "### ADR-audit-window" in section
    assert "## Decision" in section                     # file body inlined verbatim
    assert "content not in-store" not in section


def test_packet_marks_a_missing_adr_instead_of_failing():
    store = Store.load(DANGLING)
    packet = render_packet(store, DANGLING, "TASK-9997", ["RU-0104"], now=NOW)
    assert "ADR-ghost (missing from spec/rationale/" in packet
