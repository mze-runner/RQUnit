"""Context assembly (TASK-091, spec §9, packet layout formats §6).

The assembler answers queries; it never orchestrates. Every assembly
materializes as an immutable packet — the complete and exact store-derived
context the agent received, with manifest references recorded RESOLVED and
the manifest/model hashes at assembly time. Re-runs version, never overwrite.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .errors import MalformedRef, UnresolvedRef
from .lints.base import manifest_value_leaves
from .parser.tokens import extract
from .status import compute
from .store import Ru, Store

K_CAP = 8


# ------------------------------------------------------------ resolution rendering

def _render_resolved(store: Store, kind: str, key: str, resolved) -> str:
    value = resolved.value
    if kind == "value":
        return str(value)
    if kind == "endpoint":
        return f"{value['method']} {value['path']} ({value['access']})"
    if kind == "problem":
        return f"{value['status']} {value['uri']}"
    if kind == "audit":
        return f"audit {value['code']} [{', '.join(value.get('fields') or [])}]"
    if kind == "message":
        return f"{value['direction']} '{value['subject']}' → {value['payload']}"
    if kind == "channel":
        return f"upgrade {value['upgrade_path']} ({value['access']})"
    if kind == "frame":
        return f"{value['direction']} {value['payload']}"
    if kind == "vocab":
        return "{" + ", ".join(map(str, value)) + "}"
    return str(value)


def resolve_statement(store: Store, ru: Ru) -> str:
    """Statement with every token replaced by its resolved value + the fixed
    provenance marker `⟨{ref} = value⟩` (formats §6, plan D-P8.3)."""
    statement = " ".join(ru.raw["statement"].split())
    tokens, _ = extract(statement)
    scope = store.scope_service(ru)
    for token in sorted(tokens, key=lambda t: -t.start):  # right-to-left keeps offsets valid
        try:
            resolved = store.resolve_ref(token.raw, scope)
        except (MalformedRef, UnresolvedRef):
            continue  # lint territory; the packet renders what resolves
        rendered = _render_resolved(store, token.kind, token.key, resolved)
        replacement = f"{rendered} ⟨{token.raw} = {rendered}⟩"
        statement = statement[:token.start] + replacement + statement[token.start + len(token.raw):]
    return statement


def _computed_label(store: Store, ru: Ru) -> str:
    s = compute(store, ru)
    if s.failing:
        return "failing"
    if s.blocked:
        return "blocked"
    if s.done:
        return "done"
    if s.debt:
        return "debt"
    return "pending"


def render_ru(store: Store, ru: Ru, full: bool = True) -> list[str]:
    """An RU render = id, statement (resolved), verification list with current
    computed status, tags (formats §6)."""
    out = [f"### {ru.id}" + (f" — {ru.tier}" if ru.tier != "standard" else ""), ""]
    out.append(resolve_statement(store, ru))
    out.append("")
    if not full:
        return out
    feat_id = ru.raw.get("feature")
    if feat_id:
        feat = next((f for f in store.features() if f.id == feat_id), None)
        if feat:
            goal = " ".join(feat.raw["goal"].split())
            out += [f"Feature goal ({feat_id}): {goal}", ""]
    label = _computed_label(store, ru)
    out.append(f"Verification (computed: {label}):")
    for entry in ru.raw.get("verification") or []:
        ref = entry.get("ref") or f"criterion: {entry.get('criterion')}"
        out.append(f"- {entry['type']}: {ref}")
    out.append("")
    out.append(f"Tags: {', '.join(ru.raw.get('tags') or [])}")
    out.append("")
    return out


# ------------------------------------------------------------ star map

def render_surface_sheet(store: Store, service: str) -> list[str]:
    manifest = store.manifests()[service]
    raw = manifest.raw
    out = [f"### {service} (manifest hash {manifest.content_hash[:19]}…)", ""]
    endpoints = raw.get("endpoints") or []
    if endpoints:
        out += ["| method | path | access | planned | ru |", "|---|---|---|---|---|"]
        for e in endpoints:
            out.append(f"| {e['method']} | {e['path']} | {e['access']} | "
                       f"{'yes' if e.get('planned') else ''} | {e['ru']} |")
        out.append("")
        default_policy = (raw.get("defaults") or {}).get("unknown_fields")
        for e in endpoints:
            out += render_endpoint_shapes(e, default_policy)
    messages = raw.get("messages") or []
    if messages:
        out += ["| direction | subject | payload | ru |", "|---|---|---|---|"]
        for m in messages:
            out.append(f"| {m['direction']} | {m['subject']} | {m['payload']} | {m['ru']} |")
        out.append("")
    channels = raw.get("channels") or []
    for c in channels:
        frames = ", ".join(f"{f['id']}({f['direction']})" for f in c.get("frames") or [])
        out.append(f"- channel {c['id']}: upgrade {c['upgrade_path']} ({c['access']}) frames: {frames}")
    if channels:
        out.append("")
    leaves = manifest_value_leaves(raw.get("values") or {})
    if leaves:
        out.append("Values: " + "; ".join(f"{k}={v}" for k, v in sorted(leaves.items())))
        out.append("")
    return out


def render_field(field: dict) -> str:
    """One census row. Absences and rejections are rendered as loudly as
    presences — `never` and `forbidden` are the claims an implementer is most
    likely to break, and a packet that omits them reads as permission."""
    parts = [field["presence"]]
    if field.get("in"):
        parts.append(f"in {field['in']}")
    if field.get("type"):
        parts.append(field["type"])
        if field.get("items"):
            parts.append(f"of {field['items']}")
    if field.get("nullable") is not None:
        parts.append("nullable" if field["nullable"] else "never null")
    if field.get("vocab"):
        parts.append(f"values ∈ {field['vocab']}")
    for key in ("max_chars", "min_chars", "min", "max", "min_items", "max_items"):
        if field.get(key) is not None:
            parts.append(f"{key} {field[key]}")
    line = f"- `{field['name']}` ({', '.join(parts)})"
    if field.get("note"):
        line += f" — {field['note']}"
    return line


def render_endpoint_shapes(endpoint: dict, default_policy: str | None) -> list[str]:
    """Both directions of one surface (§5.9).

    Packets exist so an implementing agent never has to read the store. Once a
    shape lives on the endpoint rather than in a contract file, a packet that
    renders only the route table hides the very census the RU depends on — so
    the shapes follow the edge. `none` renders explicitly, because "carries
    nothing" is a claim and silence is not.
    """
    out: list[str] = []
    for direction in ("inbound", "outbound"):
        slot = endpoint.get(direction)
        if slot is None:
            continue
        header = f"**{endpoint['id']} · {direction}**"
        if direction == "outbound" and isinstance(slot, dict):
            header += f" — status {slot.get('status')}"
        if slot == "none":
            out += [f"{header} — declared empty: carries no body.", ""]
            continue
        if direction == "inbound":
            policy = slot.get("unknown_fields", default_policy)
            if policy:
                header += f" — undeclared fields: {policy}"
        fields = slot.get("fields")
        if fields == "none" or not fields:
            out += [f"{header} — declared empty: carries no body.", ""]
            continue
        out += [header, ""]
        out += [render_field(f) for f in fields]
        out.append("")
    return out


def render_contract(contract) -> list[str]:
    """A contract render (formats §11): the packet-only implementer must know
    the wire shape without reading the store — including the absences."""
    raw = contract.raw
    out = [f"### {contract.id} (contract hash {contract.content_hash[:19]}…)", ""]
    header = " ".join(raw["description"].split())
    if raw.get("access_tier"):
        header += f" — consumed by `{raw['access_tier']}`-tier surfaces"
    out += [header, ""]
    for field in raw.get("fields") or []:
        parts = [field.get("where", "claims"), field["presence"]]
        if field.get("type"):
            parts.append(field["type"])
        if field.get("vocab"):
            parts.append(f"values ∈ {field['vocab']}")
        line = f"- `{field['name']}` ({', '.join(parts)})"
        if field.get("note"):
            line += f" — {field['note']}"
        out.append(line)
    out.append("")
    return out


# ------------------------------------------------------------ one-hop background

def one_hop(store: Store, task_rus: list[Ru]) -> tuple[list[Ru], list[str]]:
    task_ids = {ru.id for ru in task_rus}
    task_features = {ru.raw.get("feature") for ru in task_rus if ru.raw.get("feature")}
    task_tags = set().union(*({*(ru.raw.get("tags") or [])} for ru in task_rus))
    task_owns = [g for ru in task_rus for g in (ru.raw.get("scope") or {}).get("owns") or []]
    supersession = {ru.raw.get("supersedes") for ru in task_rus} - {None}

    def owns_overlap(ru: Ru) -> bool:
        for a in (ru.raw.get("scope") or {}).get("owns") or []:
            for b in task_owns:
                if a == b or a.startswith(b.rstrip("/*") + "/") or b.startswith(a.rstrip("/*") + "/"):
                    return True
        return False

    candidates = []
    for ru in store.rus():
        if ru.id in task_ids or ru.status != "active" or ru.tier == "constitutional":
            continue
        linked = ru.id in supersession or ru.raw.get("supersedes") in task_ids
        if not (linked or owns_overlap(ru)):
            continue
        feature_shared = 1 if ru.raw.get("feature") in task_features else 0
        tag_overlap = len(task_tags & set(ru.raw.get("tags") or []))
        candidates.append(((-feature_shared, -tag_overlap, ru.id), ru))
    candidates.sort(key=lambda pair: pair[0])
    ranked = [ru for _, ru in candidates]
    return ranked[:K_CAP], [ru.id for ru in ranked[K_CAP:]]


# ------------------------------------------------------------ packet

def _store_commit(root: Path) -> str:
    proc = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                          capture_output=True, text=True)
    sha = proc.stdout.strip()
    dirty = subprocess.run(["git", "-C", str(root), "status", "--porcelain"],
                           capture_output=True, text=True).stdout.strip()
    return "WORKTREE" if (proc.returncode != 0 or not sha or dirty) else sha


def render_packet(store: Store, root: Path, task: str, ru_ids: list[str],
                  now: str | None = None) -> str:
    by_id = {ru.id: ru for ru in store.rus()}
    missing = [r for r in ru_ids if r not in by_id]
    if missing:
        raise ValueError(f"unknown RU id(s): {', '.join(missing)}")
    task_rus = [by_id[r] for r in ru_ids]
    constitutional = [ru for ru in store.rus()
                      if ru.tier == "constitutional" and ru.status == "active"]

    touched = sorted({s for ru in task_rus if (s := store.scope_service(ru))})
    manifests = store.manifests()
    hash_services = [s for s in touched + ["shared"] if s in manifests]
    model_ids = sorted({e["ref"].removeprefix("MDL-") for ru in task_rus
                        for e in ru.raw.get("verification") or [] if e.get("type") == "model"})
    models = store.models()

    inline, ids_only = one_hop(store, task_rus)

    owns = sorted({g for ru in task_rus for g in (ru.raw.get("scope") or {}).get("owns") or []})
    mnt: dict[str, str] = {}
    for ru in task_rus:
        for glob in (ru.raw.get("scope") or {}).get("must_not_touch") or []:
            mnt.setdefault(glob, ru.id)

    out = [
        "---",
        f"task: {task}",
        f"generated_at: {now or datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"store_commit: {_store_commit(root)}",
        "hashes:",
        "  manifests: {" + ", ".join(f"{s}: \"{manifests[s].content_hash}\"" for s in hash_services) + "}",
        "  models: {" + ", ".join(f"MDL-{m}: \"{models[m].content_hash}\"" for m in model_ids if m in models) + "}",
        "---",
        "# 0. Constitutional requirements",
        "",
    ]
    for ru in constitutional:
        out += render_ru(store, ru)
    out += ["# 1. Task requirements", ""]
    for ru in task_rus:
        out += render_ru(store, ru)
    out += ["# 2. Interface star map", ""]
    for service in touched:
        out += render_surface_sheet(store, service)
    ct_ids = sorted({str(e.get("ref")) for ru in task_rus
                     for e in ru.raw.get("verification") or []
                     if e.get("type") == "contract"
                     and not str(e.get("ref", "")).startswith("TODO(")})
    for ct_id in ct_ids:
        contract = store.contracts().get(ct_id)
        if contract is None:
            out += [f"- {ct_id} (missing from spec/contracts/ — an L5 error)", ""]
            continue
        out += render_contract(contract)
    out += ["# 3. Rationale", ""]
    adrs = sorted({ru.raw["rationale_ref"] for ru in task_rus if ru.raw.get("rationale_ref")})
    for adr_id in adrs:
        adr_path = store.adr_path(adr_id)
        if adr_path is None:
            out += [f"- {adr_id} (missing from spec/rationale/ — an L7 error)", ""]
        else:
            out += [f"### {adr_id}", "", adr_path.read_text().strip(), ""]
    if not adrs:
        out += ["_no linked ADRs_", ""]
    for model_id in model_ids:
        model = models.get(model_id)
        if model is None:
            continue
        out.append(f"Model MDL-{model_id} ({model.content_hash}):")
        for state in sorted(model.raw["states"]):
            for event, target in sorted((model.raw["states"][state].get("on") or {}).items()):
                out.append(f"- {state} --{event}--> {target}")
        out.append("")
    out += ["# 4. Background (read-only)", ""]
    for ru in inline:
        out += render_ru(store, ru, full=False)
    if ids_only:
        out.append("Further: " + ", ".join(ids_only))
        out.append("")
    if not inline and not ids_only:
        out += ["_no one-hop neighbours_", ""]
    out += ["# 5. Boundaries", "", "```yaml", f"task: {task}",
            f"owns: [{', '.join(owns)}]"]
    if mnt:
        out.append("must_not_touch:")
        out += [f"  - {{ glob: {glob}, ru: {ru_id} }}" for glob, ru_id in sorted(mnt.items())]
    else:
        out.append("must_not_touch: []")
    out += ["```", ""]
    return "\n".join(out)


def packet_path(root: Path, task: str) -> Path:
    """Next free versioned path — packets are immutable, re-runs version
    (formats decision 5, plan D-P8.4)."""
    packets = Path(root) / "spec" / "packets"
    base = packets / f"{task}.packet.md"
    if not base.exists():
        return base
    version = 2
    while (packets / f"{task}.v{version}.packet.md").exists():
        version += 1
    return packets / f"{task}.v{version}.packet.md"
