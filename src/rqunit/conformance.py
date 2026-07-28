"""Manifest ↔ code conformance (spec §5.6, §5.8) — the diff, written once.

The inversion that makes the framework language-neutral: a per-stack adapter
EXTRACTS what the code exposes into `actual-surface.json` (pinned schema in
interfaces/), and this module owns every judgment about what a difference
MEANS. Adapters never decide; they only observe. A new language therefore
costs an extractor, not a reconciler.

Divergence classes:
  CF1 declared surface the code does not serve
  CF2 surface the code serves that no manifest declares
  CF3 implemented, but the manifest still marks it planned (§5.8)
  CF4 access tier disagrees between manifest and code composition
  CF5 declared outbound message the code never publishes
  CF6 message the code publishes that no manifest declares

Ratified exceptions travel inside the artifact and downgrade a divergence to
a `finding` — reported with its justification, never silenced (§6.6: drift is
disposed of visibly or not at all).
"""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError

from .errors import BadConfig
from .store import Store
from .violations import Violation

SCHEMA_PATH = Path(__file__).parent / "interfaces" / "actual-surface.schema.json"

_SUGGESTION = {
    "CF1": "Implement the surface, mark it `planned: true` until it lands (§5.8), or delete the "
           "manifest entry at Gate 1 — a declared surface that does not exist is a promise the "
           "code never made.",
    "CF2": "Declare it in the owning manifest at Gate 1 (with its governing RU), or delete the "
           "code — an undeclared surface is ungoverned by definition.",
    "CF3": "Flip `planned` off at Gate 1 (a mutating manifest edit, §5.5) — the surface shipped, "
           "so its RU is now claimable.",
    "CF4": "Align the code's middleware composition with the declared tier, or re-declare the "
           "tier at Gate 1. If the difference is deliberate, record it as an exception with a "
           "justification in the adapter's artifact.",
    "CF5": "Publish it, mark it `planned: true`, or remove the declaration — a declared outbound "
           "message nobody emits is a contract with no counterparty.",
    "CF6": "Declare the message in the manifest at Gate 1, or stop publishing it.",
}


def load_actual(path: Path) -> dict:
    """Read and schema-validate an adapter artifact. A malformed artifact is a
    configuration error, not a conformance failure — we cannot judge a surface
    we cannot read."""
    path = Path(path)
    if not path.is_file():
        raise BadConfig(str(path), "no actual-surface artifact — run the stack's extractor "
                                   "(Rust: `cargo run -p spec-conformance-tests --bin "
                                   "extract-surface`) or point [stacks.*] actual_surface at it")
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise BadConfig(str(path), f"not parseable JSON: {e}") from e
    schema = json.loads(SCHEMA_PATH.read_text())
    try:
        Draft202012Validator(schema).validate(data)
    except ValidationError as e:
        raise BadConfig(str(path), f"does not match the actual-surface contract: {e.message}") from e
    return data


def _exception_for(data: dict, rule: str, service: str, target: str) -> str | None:
    for entry in data.get("exceptions") or []:
        if (entry["rule"] == rule and entry["service"] == service
                and entry["target"] == target):
            return entry["justification"]
    return None


def reconcile(store: Store, actual: dict, path: Path | None = None) -> list[Violation]:
    """Every divergence between the manifests and one adapter artifact."""
    out: list[Violation] = []
    where = str(path) if path else "actual-surface.json"
    manifests = store.manifests()

    def emit(rule: str, service: str, target: str, message: str) -> None:
        justification = _exception_for(actual, rule, service, target)
        if justification:
            out.append(Violation(
                rule=rule, severity="finding", artifact=f"{service}:{target}", path=where,
                message=f"{message} — RATIFIED EXCEPTION: {justification}",
                suggestion="Re-examine at the next Gate 1 sitting: an exception that outlives its "
                           "reason becomes camouflage."))
        else:
            out.append(Violation(
                rule=rule, severity="error", artifact=f"{service}:{target}", path=where,
                message=message, suggestion=_SUGGESTION[rule]))

    for service, surface in (actual.get("services") or {}).items():
        manifest = manifests.get(service)
        if manifest is None:
            out.append(Violation(
                rule="CF2", severity="error", artifact=service, path=where,
                message=f"the adapter reports a surface for '{service}', which has no manifest.",
                suggestion="Add spec/manifests/<service>.manifest.yaml, or stop extracting a "
                           "service the store does not govern."))
            continue

        # ---- endpoints
        declared: dict[tuple[str, str], dict] = {
            (e["method"], e["path"]): e for e in manifest.raw.get("endpoints") or []}
        served: dict[tuple[str, str], dict] = {
            (e["method"], e["path"]): e for e in surface.get("endpoints") or []}

        for key, entry in sorted(declared.items()):
            target = f"{key[0]} {key[1]}"
            if key not in served:
                if not entry.get("planned"):
                    emit("CF1", service, target,
                         f"declared endpoint {target} is not served by the code")
                continue  # planned + absent is the expected asymmetry (§5.8)
            if entry.get("planned"):
                emit("CF3", service, target,
                     f"endpoint {target} is served but the manifest still marks it planned")
                continue
            actual_tier = served[key].get("access")
            if actual_tier and actual_tier != entry["access"]:
                emit("CF4", service, target,
                     f"access tier for {target} disagrees: manifest '{entry['access']}', "
                     f"code '{actual_tier}'")

        for key in sorted(served):
            if key not in declared:
                emit("CF2", service, f"{key[0]} {key[1]}",
                     f"endpoint {key[0]} {key[1]} is served but no manifest declares it")

        # ---- messages (presence-based: adapters that cannot resolve direction omit it)
        published = {m["subject"] for m in surface.get("messages") or []}
        declared_subjects = {m["subject"] for m in manifest.raw.get("messages") or []}
        for message in manifest.raw.get("messages") or []:
            if (message.get("direction") == "outbound" and not message.get("planned")
                    and not message.get("external")
                    and message["subject"] not in published):
                emit("CF5", service, message["subject"],
                     f"declared outbound message '{message['subject']}' is never published by the code")
        for subject in sorted(published - declared_subjects):
            emit("CF6", service, subject,
                 f"the code publishes '{subject}', which no manifest declares")

    return out


def run(store: Store, root: Path, artifacts: list[Path]) -> list[Violation]:
    out: list[Violation] = []
    for path in artifacts:
        out.extend(reconcile(store, load_actual(path), path))
    return out
