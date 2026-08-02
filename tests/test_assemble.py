"""TASK-090/091 acceptance: golden-packet determinism (modulo the two allowed
front-matter lines), the k=8 cap in documented rank order, no-overwrite
versioning, the hash-proof (a later manifest edit never changes a written
packet), the Boundaries round-trip through the Phase 5 hook parser, and the
ru-index shape."""

import json
import shutil
from pathlib import Path

import pytest

from rqunit.assemble import one_hop, packet_path, render_packet, render_surface_sheet
from rqunit.generate import render_ru_index
from rqunit.hooks import load_boundaries
from rqunit.store import Store

FIXTURES = Path(__file__).parent.parent / "fixtures"
ASSEMBLY = FIXTURES / "store" / "assembly"
TASK_RUS = ["RU-0010", "RU-0011"]
NOW = "2026-07-25T12:00:00+00:00"


def _packet(root=ASSEMBLY) -> str:
    store = Store.load(root)
    return render_packet(store, root, "TASK-0100", TASK_RUS, now=NOW)


def _stable(content: str) -> str:
    return "\n".join(l for l in content.splitlines()
                     if not l.startswith(("generated_at:", "store_commit:")))


# ------------------------------------------------------------ golden packet

def test_packet_is_byte_deterministic_modulo_allowed_front_matter():
    assert _stable(_packet()) == _stable(_packet())


def test_packet_sections_in_formats_order_with_resolved_refs():
    packet = _packet()
    positions = [packet.index(h) for h in (
        "# 0. Constitutional requirements", "# 1. Task requirements",
        "# 2. Interface star map", "# 3. Rationale",
        "# 4. Background (read-only)", "# 5. Boundaries")]
    assert positions == sorted(positions)
    assert "RU-0001" in packet.split("# 1.")[0]        # constitutional first, always
    # fixed provenance form (plan D-P8.3)
    assert "90 ⟨{value:retention.decision_log_days} = 90⟩" in packet
    assert "DELETE /api/v1/orders/{id} (protected) ⟨{endpoint:cancel_order} =" in packet
    assert "manifests: {service-orders:" in packet     # hashes recorded at assembly time


def test_one_hop_cap_is_eight_inline_plus_ids_only_in_rank_order():
    store = Store.load(ASSEMBLY)
    task_rus = [ru for ru in store.rus() if ru.id in TASK_RUS]
    inline, ids_only = one_hop(store, task_rus)
    assert len(inline) == 8 and len(ids_only) == 4
    # rank: FEAT-hot sharers (5) first, then tag-overlap, then id order
    assert [ru.id for ru in inline[:5]] == [f"RU-00{n}" for n in range(20, 25)]
    assert all(set(ru.raw["tags"]) & {"orders"} for ru in inline[5:])
    assert ids_only == ["RU-0028", "RU-0029", "RU-0030", "RU-0031"]
    packet = _packet()
    assert "Further: RU-0028, RU-0029, RU-0030, RU-0031" in packet


def test_boundaries_round_trip_through_the_h1_parser(tmp_path):
    root = tmp_path / "store"
    shutil.copytree(ASSEMBLY, root)
    store = Store.load(root)
    content = render_packet(store, root, "TASK-0100", TASK_RUS, now=NOW)
    target = packet_path(root, "TASK-0100")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    boundaries = load_boundaries(target)
    assert boundaries.task == "TASK-0100"
    assert "service-orders/fulfilment" in boundaries.owns
    assert boundaries.must_not_touch == [{"glob": "service-billing", "ru": "RU-0010"}]


def test_rerun_versions_never_overwrites(tmp_path):
    root = tmp_path / "store"
    shutil.copytree(ASSEMBLY, root)
    (root / "spec" / "packets").mkdir(parents=True, exist_ok=True)
    first = packet_path(root, "TASK-0100")
    first.write_text("original")
    assert packet_path(root, "TASK-0100").name == "TASK-0100.v2.packet.md"
    (root / "spec" / "packets" / "TASK-0100.v2.packet.md").write_text("second")
    assert packet_path(root, "TASK-0100").name == "TASK-0100.v3.packet.md"
    assert first.read_text() == "original"


def test_committed_packet_is_immune_to_later_manifest_edits(tmp_path):
    root = tmp_path / "store"
    shutil.copytree(ASSEMBLY, root)
    store = Store.load(root)
    target = packet_path(root, "TASK-0100")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_packet(store, root, "TASK-0100", TASK_RUS, now=NOW))
    snapshot = target.read_bytes()
    manifest = root / "spec" / "manifests" / "service-orders.manifest.yaml"
    manifest.write_text(manifest.read_text().replace("decision_log_days: 90",
                                                     "decision_log_days: 30"))
    fresh = render_packet(Store.load(root), root, "TASK-0100", TASK_RUS, now=NOW)
    assert target.read_bytes() == snapshot                 # flight recorder intact
    assert "30 ⟨{value:retention.decision_log_days} = 30⟩" in fresh  # re-runs see the new world
    assert "= 90⟩" in snapshot.decode()


def test_unknown_ru_refs_are_rejected():
    store = Store.load(ASSEMBLY)
    with pytest.raises(ValueError, match="RU-9999"):
        render_packet(store, ASSEMBLY, "TASK-0100", ["RU-9999"])


# ------------------------------------------------------------ ru-index (TASK-090)

def test_ru_index_carries_the_formats_fields():
    # Shape invariants only — computed labels and per-RU specifics are live
    # state and must never be pinned in tests (they change with every batch).
    index = json.loads(render_ru_index(Store.load(FIXTURES / "store" / "valid")))
    assert index["rus"], "index must not be empty"
    required = {"id", "status", "tier", "computed", "tags", "feature",
                "owns", "must_not_touch", "verification_types", "manifest_refs"}
    labels = {"done", "blocked", "failing", "debt", "pending"}
    for row in index["rus"]:
        assert required <= set(row), row["id"]
        assert row["computed"] in labels, row["id"]
    assert any(row["tier"] == "constitutional" for row in index["rus"])


# ------------------------------------------------------------ v0.13 shapes

def test_star_map_carries_the_census_the_ru_depends_on():
    """Packets exist so an implementing agent never has to read the store. Once
    a shape lives on the endpoint rather than in a contract file, a packet that
    renders only the route table hides the very thing the RU asserts about."""
    sheet = "\n".join(render_surface_sheet(Store.load(ASSEMBLY), "service-orders"))
    assert "cancel_order · inbound" in sheet
    assert "`id` (required, in path, string)" in sheet


def test_declared_empty_is_rendered_not_omitted():
    """`none` is a claim; silence is not. A packet that prints nothing for an
    empty direction reads as 'unspecified' — the opposite of what it says."""
    sheet = "\n".join(render_surface_sheet(Store.load(ASSEMBLY), "service-orders"))
    assert "outbound** — status 204 — declared empty" in sheet


def test_negative_claims_render_as_loudly_as_positive_ones():
    from rqunit.assemble import render_field

    leak = render_field({"name": "cost_basis", "presence": "never",
                         "note": "internal pricing never leaves"})
    reject = render_field({"name": "id", "presence": "forbidden", "note": "server-owned"})
    assert "`cost_basis` (never)" in leak and "never leaves" in leak
    assert "`id` (forbidden)" in reject
    # An implementer skimming a packet must not be able to mistake an absence
    # claim for an omission — these are the claims most likely to be broken.
    assert "never" in leak and "forbidden" in reject


def test_bounds_and_nullability_reach_the_packet():
    from rqunit.assemble import render_field

    line = render_field({"name": "note", "presence": "optional", "type": "string",
                         "nullable": True, "max_chars": 200})
    assert "max_chars 200" in line and "nullable" in line
    strict = render_field({"name": "email", "presence": "always", "type": "string",
                           "nullable": False})
    assert "never null" in strict
