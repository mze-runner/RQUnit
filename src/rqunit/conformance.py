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
  CF7 the route matches, but its declared shape and the code's disagree
  CF8 two routes serve the same type while declaring different censuses
  CF9 a declared surface family that no probe examined
  CF10 a declared audit event the code never emits
  CF11 an audit code the code emits that no manifest declares

Ratified exceptions live in the STORE, at
`spec/framework/conformance-exceptions.yaml`, and downgrade a divergence to a
`finding` — reported with its justification, never silenced (§6.6: drift is
disposed of visibly or not at all). They used to ride inside the adapter
artifact; they no longer may. Everything a probe emits is an OBSERVATION this
module judges, but an exception is a JUDGMENT that overrides it, and those
cannot share a channel once probes can be written by anyone: a probe able to
author its own waivers could turn its own mistakes green. A waiver is a
reviewed human decision, so it lives where Gate 1 can see it.
"""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError

import yaml

from .errors import BadConfig
from .pathnorm import normalize
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
           "tier at Gate 1. If the difference is deliberate, ratify it in "
           "spec/framework/conformance-exceptions.yaml with a justification.",
    "CF5": "Publish it, mark it `planned: true`, or remove the declaration — a declared outbound "
           "message nobody emits is a contract with no counterparty.",
    "CF6": "Declare the message in the manifest at Gate 1, or stop publishing it.",
    "CF7": "Declare the field, or stop carrying it. A census the code contradicts is worse than "
           "none: it reads as reviewed. If the difference is deliberate — a field the serializer "
           "suppresses at runtime — ratify it in spec/framework/conformance-exceptions.yaml.",
    "CF8": "Reconcile the two censuses, or stop serving one type from both routes. Shapes are "
           "declared per surface, so the code's type is what says two of them are the same "
           "thing — and one of the two declarations is stale.",
    "CF9": "Run a probe that covers this family and commit its artifact, or remove the "
           "declaration. A family nobody examined is not a passing family — it is an unasked "
           "question, and a green run that never asked it is the failure this rule exists for.",
    # No id here. `RU-0002` is what audit-on-mutation is called in this product's
    # own reference fixtures; a consumer store seeds no RUs, so the citation named
    # an artifact that existed nowhere in the store reading the message.
    "CF10": "Emit the event, mark the governing RU not-done, or delete the declaration at Gate 1. "
            "An audit event nobody records is an evidence trail that does not exist, and a "
            "state-changing surface without one cannot show what it did.",
    "CF11": "Declare it in `audit_events` at Gate 1 with its census and retention, or stop "
            "emitting it. An undeclared audit record is evidence with no retention rule and no "
            "forbidden-field check — the two things that make it evidence.",
}

FAMILIES = ("endpoints", "messages", "channels", "audit_events")

# Field-level proof classes (§5.6). A manifest may exceed what an extractor can
# see — that is how it carries target state — so what is UNPROVEN has to be
# countable rather than invisible.
EXTRACTOR_CONFIRMED = "extractor-confirmed"
UNPROVEN = "unproven"


def load_actual(path: Path) -> dict:
    """Read and schema-validate an adapter artifact. A malformed artifact is a
    configuration error, not a conformance failure — we cannot judge a surface
    we cannot read."""
    path = Path(path)
    if not path.is_file():
        raise BadConfig(str(path), "no actual-surface artifact — run the stack's extractor "
                                   "(Rust: `cargo run -p spec-conformance-tests --bin "
                                   "extract-surface`) or point [stacks.<name>.adapter] "
                                   "extractor = { artifact = \"...\" } at it")
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise BadConfig(str(path), f"not parseable JSON: {e}") from e
    reject_exceptions(data, str(path))
    schema = json.loads(SCHEMA_PATH.read_text())
    try:
        Draft202012Validator(schema).validate(data)
    except ValidationError as e:
        raise BadConfig(str(path), f"does not match the actual-surface contract: {e.message}") from e
    return data


def reject_exceptions(data: dict, where: str) -> None:
    """Applies to every transport — a cmd-mode probe could smuggle waivers on
    stdout just as easily as an artifact file could."""
    if "exceptions" in data:
        raise BadConfig(
            where,
            "this artifact carries `exceptions`, which adapters may no longer author. A waiver "
            "is a reviewed decision, not an observation: move each entry to "
            "spec/framework/conformance-exceptions.yaml, where Gate 1 governs it (§5.6). An "
            "extractor observes; it does not get to excuse what it observed.")


EXCEPTIONS_PATH = ("spec", "framework", "conformance-exceptions.yaml")
MIN_JUSTIFICATION = 20


def load_exceptions(root: Path) -> list[dict]:
    """Ratified divergences from the store. Absent file means none.

    Validated here rather than by JSON Schema because the rule that matters is
    not structural: a justification has to be long enough to be an argument. A
    one-word waiver passes any shape check and defends nothing."""
    path = Path(root).joinpath(*EXCEPTIONS_PATH)
    if not path.is_file():
        return []
    data = yaml.safe_load(path.read_text()) or {}
    entries = data.get("exceptions") or []
    if not isinstance(entries, list):
        raise BadConfig(str(path), "`exceptions` must be a list of ratified divergences")
    for entry in entries:
        missing = {"rule", "service", "target", "justification"} - set(entry or {})
        if missing:
            raise BadConfig(str(path), f"exception is missing {', '.join(sorted(missing))}")
        if len(str(entry["justification"]).strip()) < MIN_JUSTIFICATION:
            raise BadConfig(
                str(path),
                f"exception for {entry['rule']} on {entry['target']!r} has no substantive "
                "justification — an exception nobody can defend in prose is a defect wearing "
                "a waiver (§5.6)")
    return entries


def _exception_for(exceptions: list[dict], rule: str, service: str, target: str) -> str | None:
    for entry in exceptions:
        if (entry["rule"] == rule and entry["service"] == service
                and entry["target"] == target):
            return entry["justification"]
    return None


def reconcile(store: Store, actual: dict, path: Path | None = None,
              exceptions: list[dict] | None = None) -> list[Violation]:
    """Every divergence between the manifests and the assembled surface."""
    out: list[Violation] = []
    where = str(path) if path else "actual-surface.json"
    manifests = store.manifests()
    if exceptions is None:
        exceptions = load_exceptions(store.root)

    def emit(rule: str, service: str, target: str, message: str) -> None:
        justification = _exception_for(exceptions, rule, service, target)
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

    covered_by_service = actual.get("_covered")
    for service, surface in (actual.get("services") or {}).items():
        covered = set(
            (covered_by_service or {}).get(service, actual.get("covers") or FAMILIES))
        manifest = manifests.get(service)
        if manifest is None:
            out.append(Violation(
                rule="CF2", severity="error", artifact=service, path=where,
                message=f"the adapter reports a surface for '{service}', which has no manifest.",
                suggestion="Add spec/manifests/<service>.manifest.yaml, or stop extracting a "
                           "service the store does not govern."))
            continue

        # ---- endpoints
        # Guarded by coverage: a probe that never looked at routes must not have
        # its silence read as "the code serves none".
        # Identity is the NORMALIZED path: `/orders/{id}` and `/orders/:id` are
        # one route spelled by two frameworks, and matching raw strings would
        # report a CF1/CF2 pair for every parameterized route in the store.
        # Placeholder NAMES are reconciled by C12 against the `in: path` fields,
        # which is the only place a name carries meaning.
        declared: dict[tuple[str, str], dict] = {
            (e["method"], normalize(e["path"])): e
            for e in (manifest.raw.get("endpoints") or [] if "endpoints" in covered else [])}
        served: dict[tuple[str, str], dict] = {
            (e["method"], normalize(e["path"])): e
            for e in (surface.get("endpoints") or [] if "endpoints" in covered else [])}

        for key, entry in sorted(declared.items()):
            target = f"{key[0]} {entry['path']}"
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
            _reconcile_shapes(emit, service, target, entry, served[key])

        for key, entry in sorted(served.items()):
            if key not in declared:
                emit("CF2", service, f"{key[0]} {entry['path']}",
                     f"endpoint {key[0]} {entry['path']} is served but no manifest declares it")

        _same_type_divergences(emit, service, declared, served)

        # ---- audit events. A route exists in a table; an emission is a call
        # site, so a probe proves the call site EXISTS and not that it runs.
        # That limit is real and is reported through the proof classes, not
        # papered over here.
        if "audit_events" in covered:
            emitted = {e["code"] for e in surface.get("audit_events") or []}
            declared_codes = {e["code"] for e in manifest.raw.get("audit_events") or []}
            for code in sorted(declared_codes - emitted):
                emit("CF10", service, code,
                     f"declared audit event '{code}' is never recorded by the code")
            for code in sorted(emitted - declared_codes):
                emit("CF11", service, code,
                     f"the code records '{code}', which no manifest declares")

        # ---- messages (presence-based: adapters that cannot resolve direction omit it)
        if "messages" not in covered:
            continue
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


NEGATIVE_PRESENCE = {"never", "forbidden"}


def _declared_names(slot) -> set[str] | None:
    """Every field name a census declares, positive or negative."""
    if not isinstance(slot, dict):
        return None
    fields = slot.get("fields")
    if not isinstance(fields, list):
        return None
    return {f.get("name") for f in fields if f.get("name")}


def _split_by_presence(slot) -> tuple[set[str], set[str]] | None:
    """(expected, must-be-absent).

    A `never` or `forbidden` field is declared precisely so that it is NOT
    there — treating its absence as a divergence inverts the claim, and
    checking only for absence misses the case that matters: the field
    appearing anyway, which is the leak the declaration exists to forbid.
    """
    if not isinstance(slot, dict):
        return None
    fields = slot.get("fields")
    if not isinstance(fields, list):
        return None
    expected, forbidden = set(), set()
    for field in fields:
        name = field.get("name")
        if not name:
            continue
        (forbidden if field.get("presence") in NEGATIVE_PRESENCE else expected).add(name)
    return expected, forbidden


def _reconcile_shapes(emit, service: str, target: str, entry: dict, observed: dict) -> None:
    """CF7 — the route matches, its shape does not.

    Only fires where BOTH sides speak: an adapter that cannot resolve a handler
    to a type omits the block, and omission means "not observed", never "empty".
    A stack whose extractor cannot see shapes therefore degrades to presence-only
    matching instead of reporting every declared field as missing.
    """
    for direction in ("inbound", "outbound"):
        seen = observed.get(direction)
        if not isinstance(seen, dict) or not isinstance(seen.get("fields"), list):
            continue
        split = _split_by_presence(entry.get(direction))
        if split is None:
            continue
        expected, forbidden = split
        code_fields = set(seen["fields"])
        type_name = seen.get("type_name") or "type"
        for name in sorted(expected - code_fields):
            emit("CF7", service, target,
                 f"{target} declares `{direction}` field '{name}', which the code's "
                 f"{type_name} does not carry")
        # The claim worth checking: a field declared never/forbidden that the
        # code carries anyway. That is the leak, or the mass-assignment hole.
        for name in sorted(forbidden & code_fields):
            emit("CF7", service, target,
                 f"{target} declares `{direction}` field '{name}' must not appear, but the "
                 f"code's {type_name} carries it")
        for name in sorted(code_fields - expected - forbidden):
            emit("CF7", service, target,
                 f"{target} carries `{direction}` field '{name}' in the code's "
                 f"{type_name}, which the manifest does not declare")


def _same_type_divergences(emit, service: str, declared: dict, served: dict) -> None:
    """CF8 — two routes serve one type while declaring different censuses.

    Shapes are declared per surface, with no shared identity in the store. The
    code's type IS that identity: if one struct answers two routes, the two
    censuses describe the same thing and cannot disagree. This is what replaces
    a spec-side shape registry — the type system already knows, and cannot
    forget the way a hand-maintained name can.
    """
    by_type: dict[tuple[str, str], list[tuple[str, set[str] | None]]] = {}
    for key, observed in served.items():
        if key not in declared:
            continue
        for direction in ("inbound", "outbound"):
            seen = observed.get(direction)
            if not isinstance(seen, dict) or not seen.get("type_name"):
                continue
            names = _declared_names(declared[key].get(direction))
            if names is None:
                continue
            target = f"{key[0]} {declared[key]['path']}"
            by_type.setdefault((direction, seen["type_name"]), []).append((target, names))

    for (direction, type_name), entries in sorted(by_type.items()):
        if len(entries) < 2:
            continue
        first_target, first_names = entries[0]
        for target, names in entries[1:]:
            if names == first_names:
                continue
            differing = sorted(names.symmetric_difference(first_names))
            emit("CF8", service, target,
                 f"{target} and {first_target} both serve `{direction}` type "
                 f"{type_name}, but their declared censuses differ on "
                 f"{', '.join(differing)}")


def run(store: Store, root: Path, artifacts: list) -> list[Violation]:
    """Assemble every probe's observation, then judge once (§5.6).

    Judging artifact-by-artifact was correct while one extractor spoke for a
    whole stack. With a probe per (language, framework) it is not: two probes
    describing one service would each report the other's surfaces as
    undeclared.

    Entries are artifact paths, or already-loaded dicts for probes core ran
    itself (cmd mode) — same observations, different transport."""
    loaded = [a if isinstance(a, dict) else load_actual(a) for a in artifacts]
    if not loaded:
        return []
    merged = merge(loaded)
    labels = [a.get("_source") if isinstance(a, dict) else str(a) for a in artifacts]
    labels = [label for label in labels if label]
    where = Path(", ".join(labels) if labels else merged["generated_by"])
    exceptions = load_exceptions(store.root)
    return (reconcile(store, merged, where, exceptions)
            + uncovered_families(store, merged))


def boundary_provenance(store: Store, artifacts: list[dict]) -> dict:
    """How much of the declared boundary anything actually evaluates (§5.6).

    A manifest is allowed to exceed what an extractor can see — that asymmetry
    is how it carries target state beside current state. The cost is that a
    green conformance run says nothing about the part no extractor reached, so
    the unproven fraction has to be COUNTABLE. Reported, never gated: this
    measures coverage of the proof mechanisms, not correctness.

    Test-proved fields are not counted here — `rqunit trace` owns that edge —
    so a field is either extractor-confirmed or, from this module's vantage,
    unproven.
    """
    observed: dict[tuple[str, str, str], set[str]] = {}
    for artifact in artifacts:
        for service, surface in (artifact.get("services") or {}).items():
            for e in surface.get("endpoints") or []:
                for direction in ("inbound", "outbound"):
                    seen = e.get(direction)
                    if isinstance(seen, dict) and isinstance(seen.get("fields"), list):
                        key = (service, e["method"], normalize(e["path"]))
                        observed.setdefault((*key, direction), set()).update(seen["fields"])

    endpoints = shapes = confirmed = unproven = 0
    for service, manifest in store.manifests().items():
        for e in manifest.raw.get("endpoints") or []:
            endpoints += 1
            for direction in ("inbound", "outbound"):
                names = _declared_names(e.get(direction))
                if names is None:
                    continue
                shapes += 1
                seen = observed.get((service, e["method"], normalize(e["path"]), direction))
                for name in names:
                    if seen is not None and name in seen:
                        confirmed += 1
                    else:
                        unproven += 1
    return {
        "endpoints": endpoints,
        "shapes_declared": shapes,
        "fields_extractor_confirmed": confirmed,
        "fields_unproven_by_extraction": unproven,
    }


def merge(artifacts: list[dict]) -> dict:
    """One view of the code from every probe that looked at it.

    Probes are per (language, framework), so several artifacts can describe one
    service: an HTTP probe and a NATS probe, or two HTTP probes for a workspace
    that mounts more than one router. Judging each artifact alone makes every
    probe report every other probe's surfaces as undeclared, and every family it
    did not examine as unserved — two correct probes, and the whole service red
    twice over. So assembly happens first and judgment once.

    Assembly is a union, never an intersection: a surface one probe saw exists
    whether or not another probe was looking for it.
    """
    services: dict[str, dict[str, list]] = {}
    covered: dict[str, set[str]] = {}
    generated_by: list[str] = []

    for artifact in artifacts:
        # No `covers` means "I examined everything" — what a single whole-stack
        # extractor asserts, and what every artifact written before this key
        # meant. Reading omission as "nothing" would silence real divergences.
        families = set(artifact.get("covers") or FAMILIES)
        if artifact.get("generated_by"):
            generated_by.append(artifact["generated_by"])
        for service, surface in (artifact.get("services") or {}).items():
            covered.setdefault(service, set()).update(families)
            bucket = services.setdefault(service, {})
            for family in families:
                entries = surface.get(family)
                if entries:
                    bucket.setdefault(family, []).extend(entries)

    return {
        "contract_version": 1,
        "generated_by": ", ".join(generated_by) or "unknown",
        "services": services,
        "_covered": {service: sorted(families) for service, families in covered.items()},
    }


def uncovered_families(store: Store, merged: dict) -> list[Violation]:
    """CF9 — a surface family the manifest declares that no probe examined.

    `covers` stops an unexamined family reading as an absent one. On its own
    that trades false errors for silence, which is worse: the run goes green
    because nobody asked. This is the other half — the manifest already says
    which families a service has, so "nobody looked" is computable and is an
    error, not a gap in the report.
    """
    out: list[Violation] = []
    covered = merged.get("_covered") or {}
    for service, manifest in store.manifests().items():
        if service == "shared" or service not in covered:
            # A service NO adapter reports on is deliberately out of scope —
            # the contract has said so since the artifact schema was written
            # ("a service absent here is not reconciled at all"). CF9 is the
            # narrower claim: some probe examined this service, and left one of
            # its declared families unlooked-at. Widening it to whole services
            # would redden every consumer running one stack across many.
            continue
        seen = set(covered.get(service) or ())
        for family in FAMILIES:
            declared = manifest.raw.get(family) or []
            if declared and family not in seen:
                out.append(Violation(
                    rule="CF9", severity="error", artifact=f"{service}:{family}",
                    path=str(manifest.path),
                    message=(f"declares {len(declared)} {family} entr"
                             f"{'y' if len(declared) == 1 else 'ies'}, but no adapter artifact "
                             f"covers `{family}` for this service — that surface was never "
                             "examined."),
                    suggestion=_SUGGESTION["CF9"]))
    return out
