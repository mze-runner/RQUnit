"""Structural health checks — the STORE's shape, not its rules.

Lints (L*) and checks (C*) judge whether artifacts obey the framework. Doctor
asks a different question: is the store itself structurally intact? Silent RU
loss from a badly resolved merge, artifacts nothing references, review records
orphaned by a renumber, a branch stale enough that activation would collide.

Findings are advisory by construction: none of them prove a violation, and
several have legitimate explanations (a model authored ahead of its RUs, a
FEAT whose members are still drafts). Exit code stays 0 unless --strict, so
doctor never becomes a gate that teaches people to ignore it.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import ROLES
from .store import ID_CEILING, ID_WIDTH, Store

_PERMANENT = re.compile(rf"^RU-([0-9]{{{ID_WIDTH}}})$")

# Ids left before the ceiling is worth warning about. Generous on purpose:
# the fix is a store-wide migration, so the warning has to arrive with enough
# runway to schedule one, and it must never fire on an ordinary store.
_HEADROOM_WARN = 100


@dataclass(frozen=True)
class Finding:
    kind: str
    severity: str      # warning | info
    message: str
    suggestion: str


def _verification_refs(store: Store, entry_type: str) -> set[str]:
    return {str(e.get("ref")) for ru in store.rus()
            for e in ru.raw.get("verification") or []
            if e.get("type") == entry_type}


def id_gaps(store: Store) -> list[Finding]:
    """A hole in the permanent-id sequence usually means an activated RU was
    lost — most often an add/add merge conflict resolved by keeping one side."""
    numbers = sorted(int(m.group(1)) for ru in store.rus()
                     if (m := _PERMANENT.match(ru.id)))
    if not numbers:
        return []
    missing = [n for n in range(numbers[0], numbers[-1] + 1) if n not in set(numbers)]
    if not missing:
        return []
    shown = ", ".join(f"RU-{n:04d}" for n in missing[:12])
    more = f" (+{len(missing) - 12} more)" if len(missing) > 12 else ""
    return [Finding(
        kind="id-gap", severity="warning",
        message=f"{len(missing)} gap(s) in the permanent id sequence: {shown}{more}.",
        suggestion="Ids are allocated consecutively, so a gap usually means an activated RU "
                   "was dropped — check `git log --diff-filter=D -- spec/ru/` around the "
                   "missing ids. A deliberate deletion is fine; an unnoticed merge loss is not.")]


def id_headroom(store: Store) -> list[Finding]:
    """Runway left before the permanent-id ceiling.

    Widening the id width is a store-wide migration in one commit, not a flag
    — so the only useful moment to learn about it is well BEFORE the sitting
    that would need it. The threshold is deliberately generous for that
    reason: a store activating a dozen units a sitting still gets months of
    notice, and no ordinary store trips it at all."""
    numbers = [int(m.group(1)) for ru in store.rus() if (m := _PERMANENT.match(ru.id))]
    if not numbers:
        return []
    remaining = ID_CEILING - max(numbers)
    if remaining > _HEADROOM_WARN:
        return []
    return [Finding(
        kind="id-headroom", severity="warning",
        message=(f"{remaining} permanent id(s) left: the highest is "
                 f"RU-{max(numbers):0{ID_WIDTH}d} and the {ID_WIDTH}-digit ceiling is "
                 f"RU-{ID_CEILING}."),
        suggestion="Plan the width migration before a sitting needs it. The width is "
                   "compiled into every schema pattern, filename and cross-reference, "
                   "so it changes store-wide in ONE commit — every id renamed, every "
                   "reference rewritten, never mixed widths (formats §1). Activation "
                   "refuses rather than crossing it, so this is runway, not breakage.")]


def orphan_artifacts(store: Store) -> list[Finding]:
    """Artifacts nothing references. Legitimate while authoring ahead of the
    RUs that will cite them — a standing entry means dead weight or a missing link."""
    out = []
    model_refs = {r.removeprefix("MDL-") for r in _verification_refs(store, "model")}
    for model_id in store.models():
        if model_id not in model_refs:
            out.append(Finding(
                kind="orphan-model", severity="info",
                message=f"MDL-{model_id} is referenced by no RU verification.",
                suggestion="A model no RU verifies against generates conformance nobody claims — "
                           "link it or remove it."))
    adr_refs = {ru.raw.get("rationale_ref") for ru in store.rus()}
    for adr_id in store.adrs():
        if adr_id not in adr_refs:
            out.append(Finding(
                kind="orphan-adr", severity="info",
                message=f"{adr_id} is referenced by no rationale_ref.",
                suggestion="Rationale nothing points at is unreachable at review time — link it "
                           "from the RUs it explains."))
    members = {ru.raw.get("feature") for ru in store.rus()}
    for feat in store.features():
        if feat.id not in members:
            out.append(Finding(
                kind="empty-feature", severity="info",
                message=f"{feat.id} groups no RUs.",
                suggestion="Expected for a bridge FEAT during migration; otherwise the feature's "
                           "requirements were never compiled."))
    return out


def dangling_reviews(store: Store, root: Path) -> list[Finding]:
    """Gate 2 records under an id no RU carries — the record survived, its
    subject did not (a merge loss, or a hand-renumber that missed the dir)."""
    reviews = Path(root) / "spec" / "reviews"
    if not reviews.is_dir():
        return []
    known = {ru.id for ru in store.rus()}
    out = []
    for directory in sorted(p for p in reviews.iterdir() if p.is_dir()):
        if directory.name not in known:
            count = len(list(directory.glob("*.yaml")))
            out.append(Finding(
                kind="dangling-review", severity="warning",
                message=f"spec/reviews/{directory.name}/ holds {count} record(s), "
                        "but no such RU exists.",
                suggestion="Records are append-only history — do not delete them. Find where the "
                           "RU went (`git log -- spec/ru/`); restore it, or note the id was retired."))
    return out


def branch_staleness(root: Path) -> list[Finding]:
    """Activation allocates ids from the local listing, so a branch behind its
    upstream can allocate ids another branch already took (§7.1). This is the
    ONLY condition under which parallel activation collides — hence the check."""
    def git(*args) -> tuple[int, str]:
        proc = subprocess.run(["git", "-C", str(root), *args],
                              capture_output=True, text=True)
        return proc.returncode, proc.stdout.strip()

    code, _ = git("rev-parse", "--abbrev-ref", "@{upstream}")
    if code != 0:
        return []          # no upstream configured — nothing to compare against
    code, behind = git("rev-list", "--count", "HEAD..@{upstream}")
    if code != 0 or not behind.isdigit() or behind == "0":
        return []
    return [Finding(
        kind="branch-behind", severity="warning",
        message=f"branch is {behind} commit(s) behind its upstream.",
        suggestion="Pull/rebase BEFORE `rqunit activate batch` — ids are allocated from the "
                   "local listing, so activating from a stale branch can allocate ids another "
                   "branch already used (the collision surfaces as an add/add merge conflict).")]


def stack_config_health(root: Path) -> list[Finding]:
    """Passthrough config is opaque to the loader by design, so its health is
    judged here, against the adapter's own manifest — the only party entitled
    to say which keys it reads. No manifest, no judgment: that state is worth
    one note, not silence, because an unvalidated typo reads as configured.
    Doctor stays advisory, so a broken manifest is itself a finding rather
    than a crash."""
    from .config import load as load_config
    from .errors import StoreError
    from .invoke import load_adapter_manifest, stack_declaration_problems

    out = []
    try:
        config = load_config(root)
    except StoreError:
        return []          # lint owns config errors; doctor does not repeat them
    for stack in config.stacks:
        try:
            manifest = load_adapter_manifest(root, stack)
        except StoreError as e:
            out.append(Finding(
                kind="stack-config", severity="warning", message=str(e),
                suggestion="Fix the adapter manifest — it is the vocabulary "
                           "authority for this stack's passthrough keys."))
            continue
        if manifest is None:
            # No manifest, no judgment — and no note either: until adapter
            # distribution ships a manifest a consumer can actually point at,
            # a finding whose fix is impossible teaches people to ignore
            # doctor, which is the one thing it must not do.
            continue
        for problem in stack_declaration_problems(root, stack):
            out.append(Finding(
                kind="stack-config", severity="warning", message=problem,
                suggestion="The adapter manifest is the vocabulary authority for "
                           "passthrough keys — align rqunit.toml with it."))
    return out


def role_wiring(root: Path) -> list[Finding]:
    """Declared roles whose command cannot be found.

    `rqunit adapter verify` proves an ADAPTER is correct; nothing proved a
    consumer wired one correctly, and the only way to find out was to run the
    verb that needed the role and watch it fail. A committed `cmd` path that
    resolves on its author's machine and nowhere else is the live case.

    Resolvability, not execution: an evidence probe runs a test suite and a
    stripper rewrites sources, so an advisory health check must not invoke
    them. `artifact` roles are exempt — their file is produced by a pipeline
    step that legitimately has not run yet, and the verb that needs it already
    says so precisely."""
    from .config import load as load_config
    from .errors import StoreError
    from .invoke import resolve_command

    out = []
    try:
        config = load_config(root)
    except StoreError:
        return []          # lint owns config errors; doctor does not repeat them
    for stack in config.stacks:
        for role_name in ROLES:
            role = getattr(stack.adapter, role_name)
            if role is None or not role.cmd:
                continue
            resolved = resolve_command(Path(root), role.cmd[0])
            if Path(resolved).exists() or shutil.which(resolved):
                continue
            out.append(Finding(
                kind="role-wiring", severity="warning",
                message=(f"[stacks.{stack.name}.adapter] {role_name} names "
                         f"'{role.cmd[0]}', which is neither a file under the store "
                         "root nor on PATH."),
                suggestion="Build the adapter in its own toolchain, or fix the path. A "
                           "path that resolves only on the machine that wrote it is "
                           "committed breakage for everyone else — the role is "
                           "unavailable until the verb that needs it fails."))
    return out


def run(store: Store, root: Path) -> list[Finding]:
    return (id_gaps(store) + id_headroom(store) + orphan_artifacts(store)
            + dangling_reviews(store, root) + branch_staleness(root)
            + stack_config_health(root) + role_wiring(root))
