"""Contracts (CT) declaration layer (spec §6.1 v0.11, formats §11).
Invariants: contracts load and validate from spec/contracts/; dangling
non-TODO refs are L5 errors while TODO(CT-…) stays legal debt; resolved refs
are fingerprinted so an unreviewed CT edit flips dependents suspect (L20 —
the ruled manifest-like governance); packets render the full shape including
absences."""

import shutil
import textwrap
from pathlib import Path

import pytest
import yaml

from rqunit.assemble import render_packet
from rqunit.canonical import expected_fingerprints, link_fingerprint
from rqunit.errors import FilenameIdMismatch, UnknownArtifact
from rqunit.lints.base import run_lints
from rqunit.store import Store

FIXTURES = Path(__file__).parent.parent / "fixtures"
WITH_CT = FIXTURES / "lints" / "L05" / "pass"      # RU-0003 → CT-base resolved + a TODO ref
NOW = "2026-07-28T12:00:00+00:00"


# ------------------------------------------------------------ loader

def test_store_loads_contracts():
    store = Store.load(WITH_CT)
    assert list(store.contracts()) == ["CT-base"]
    contract = store.contracts()["CT-base"]
    assert contract.content_hash.startswith("sha256:")
    assert contract.raw["kind"] == "claim-set"


def test_bad_contract_filenames_and_id_mismatch_are_rejected(tmp_path):
    root = tmp_path / "store"
    shutil.copytree(WITH_CT, root)
    stray = root / "spec" / "contracts" / "notes.yaml"
    stray.write_text("id: CT-notes\nkind: claim-set\ndescription: mismatched home.\n"
                     "fields:\n- { name: sub, presence: always }\n")
    with pytest.raises(UnknownArtifact):
        Store.load(root)
    stray.unlink()
    (root / "spec" / "contracts" / "CT-other.yaml").write_text(
        "id: CT-base\nkind: claim-set\ndescription: id disagrees with filename.\n"
        "fields:\n- { name: sub, presence: always }\n")
    with pytest.raises(FilenameIdMismatch):
        Store.load(root)


# ------------------------------------------------------------ L5 + fingerprints

def test_todo_ct_refs_stay_legal_debt():
    violations = [v for v in run_lints(Store.load(WITH_CT), only="L5") if v.rule == "L5"]
    assert violations == []          # resolved ref + TODO ref, both clean


def test_resolved_ct_refs_are_fingerprinted_todo_refs_are_not():
    store = Store.load(WITH_CT)
    ru = next(r for r in store.rus() if r.id == "RU-0003")
    fps = expected_fingerprints(store, ru.raw)
    assert fps.get("CT-base") == store.contracts()["CT-base"].content_hash
    assert not any(k.startswith("TODO(") for k in fps)
    assert link_fingerprint(store, "CT-ghost") is None


def test_editing_a_referenced_contract_flips_the_dependent_suspect(tmp_path):
    root = tmp_path / "store"
    shutil.copytree(WITH_CT, root)
    store = Store.load(root)
    ru_path = root / "spec" / "ru" / "RU-0003.yaml"
    raw = yaml.safe_load(ru_path.read_text())
    raw["gate1_stamp"] = {"hash": "sha256:" + "0" * 64, "by": "fixture-op",
                          "at": "2026-07-28T10:00:00+00:00"}
    raw["link_fingerprints"] = {"CT-base": store.contracts()["CT-base"].content_hash}
    ru_path.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True))
    assert [v for v in run_lints(Store.load(root), only="L20") if v.rule == "L20"] == []

    ct_path = root / "spec" / "contracts" / "CT-base.yaml"
    ct = yaml.safe_load(ct_path.read_text())
    ct["fields"].append({"name": "aud", "presence": "never"})
    ct_path.write_text(yaml.safe_dump(ct, sort_keys=False, allow_unicode=True))
    flagged = [v for v in run_lints(Store.load(root), only="L20") if v.rule == "L20"]
    assert any(v.artifact == "RU-0003" and "CT-base" in v.message for v in flagged)
    assert all(v.severity == "finding" for v in flagged)


# ------------------------------------------------------------ packet §2

def test_packet_renders_contract_shape_with_absences(tmp_path):
    root = tmp_path / "store"
    shutil.copytree(WITH_CT, root)
    ct_path = root / "spec" / "contracts" / "CT-base.yaml"
    ct_path.write_text(textwrap.dedent("""\
        id: CT-base
        kind: claim-set
        description: Access token claim set.
        access_tier: protected
        fields:
          - { name: sub, where: claims, presence: always, type: string, note: user id }
          - { name: kid, where: header, presence: always }
          - { name: iss, presence: never }
    """))
    store = Store.load(root)
    packet = render_packet(store, root, "TASK-9996", ["RU-0003"], now=NOW)
    section = packet.split("# 2. Interface star map")[1].split("# 3.")[0]
    assert "### CT-base (contract hash sha256:" in section
    assert "consumed by `protected`-tier surfaces" in section
    assert "- `sub` (claims, always, string) — user id" in section
    assert "- `kid` (header, always)" in section
    assert "- `iss` (claims, never)" in section     # absence rendered, not omitted
