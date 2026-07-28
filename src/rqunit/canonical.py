"""THE canonicalizer (formats §9). One implementation, exported — L19, L20,
and spec-activate all import from here; three implementations of "canonical"
is how canonical dies.

Canonical hash (gate stamps, RU-target fingerprints): JSON serialization of
{statement, scope, verification, tier} with keys sorted recursively, UTF-8,
no insignificant whitespace, tier defaulted to "standard" when absent.
ADR-target fingerprints: sha256 of the raw file bytes.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

NORMATIVE_FIELDS = ("statement", "scope", "verification", "tier")


def canonical_hash(ru_raw: dict) -> str:
    normative = {
        "statement": ru_raw.get("statement"),
        "scope": ru_raw.get("scope"),
        "verification": ru_raw.get("verification"),
        "tier": ru_raw.get("tier", "standard"),
    }
    payload = json.dumps(normative, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def file_fingerprint(path: Path) -> str:
    """ADR-target fingerprint: raw file bytes."""
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def link_fingerprint(store, target_id: str) -> str | None:
    """Fingerprint for one cross-artifact reference: RU targets hash their
    normative fields; ADR targets hash the raw bytes of their
    spec/rationale/<id>.md file (formats §9)."""
    if target_id.startswith("RU-"):
        target = next((r for r in store.rus() if r.id == target_id), None)
        return canonical_hash(target.raw) if target else None
    if target_id.startswith("ADR-"):
        path = store.adr_path(target_id)
        return file_fingerprint(path) if path else None
    if target_id.startswith("CT-"):
        contract = store.contracts().get(target_id)
        return contract.content_hash if contract else None
    return None


def expected_fingerprints(store, ru_raw: dict) -> dict[str, str]:
    """The link_fingerprints map an activation should record for this RU:
    every cross-artifact edge it carries (supersedes + rationale_ref +
    resolved contract verification refs)."""
    out: dict[str, str] = {}
    target = ru_raw.get("supersedes")
    if target:
        fp = link_fingerprint(store, target)
        if fp:
            out[target] = fp
    adr = ru_raw.get("rationale_ref")
    if adr:
        fp = link_fingerprint(store, adr)
        if fp:
            out[adr] = fp
    for entry in ru_raw.get("verification") or []:
        if entry.get("type") == "contract":
            ref = str(entry.get("ref", ""))
            if not ref.startswith("TODO("):
                fp = link_fingerprint(store, ref)
                if fp:
                    out[ref] = fp
    return out
