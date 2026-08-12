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

from . import ids
from .config import ROLES
from .store import ID_CEILING, ID_WIDTH, Store

# Only the DECIMAL form. A ULID intent has no ordinal and no ceiling, so
# counting one into a headroom calculation would be a category error.
_DECIMAL_INTENT = re.compile(rf"^INT-([0-9]{{{ID_WIDTH}}})$")

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


def lost_rus(store: Store, root: Path) -> list[Finding]:
    """Permanent RUs git says were deleted and that the store no longer carries.

    This replaces gap-in-the-sequence detection, which base-32 makes unsound. A
    hole was a good proxy for a lost RU only while allocation was dense, and a
    decimal-spelled store read as base-32 is sparse BY CONSTRUCTION — `0009` is
    9 and `0010` is 32, so a healthy store would be told it had thousands of
    holes and sent to hunt merge losses. Nothing distinguishes the two regimes
    per id, because `RU-0142` is a legal spelling under both.

    So the check is re-founded on evidence instead of arithmetic. History
    records the deletion; the store records what survived; the difference is
    the answer, and it is exactly as true under any future id scheme.

    A shallow clone sees no deletions and therefore reports nothing: silent
    under-reporting, never a false alarm."""
    if not shutil.which("git"):
        return []
    # `--no-renames` DELIBERATELY defeats git's default rename detection. Every
    # benign rename subtracts out anyway — a store relocating `spec/ru/` keeps
    # its ids, and activation's draft→permanent rename is excluded by name below
    # — so following renames buys nothing here and hides the one event this
    # framework says is impossible: an id rewritten in place. Under rename
    # detection that reads as a move and doctor reports a healthy store, which
    # is the query being told to look away.
    proc = subprocess.run(
        ["git", "-C", str(root), "log", "--no-renames", "--diff-filter=D",
         "--name-only", "--format=", "--", "spec/ru/"],
        capture_output=True, text=True)
    if proc.returncode != 0:
        return []                      # not a repository
    deleted = {Path(line).stem for line in proc.stdout.split()
               if line.endswith(".yaml") and not Path(line).stem.startswith("RU-draft-")}
    gone = sorted(deleted - {ru.id for ru in store.rus()})
    if not gone:
        return []
    shown = ", ".join(gone[:12])
    more = f" (+{len(gone) - 12} more)" if len(gone) > 12 else ""
    return [Finding(
        kind="lost-ru", severity="warning",
        message=f"{len(gone)} permanent RU(s) were deleted and never restored: {shown}{more}.",
        suggestion="An activated RU is append-only history — the usual cause is an add/add "
                   "merge conflict resolved by keeping one side. Find it with "
                   "`git log --diff-filter=D -- spec/ru/` and restore it, or record that the "
                   "id was retired. A deliberate deletion is fine; an unnoticed loss is not.")]


def id_headroom(store: Store) -> list[Finding]:
    """Runway left before a sequential-id ceiling — for BOTH numbered families.

    Widening the width is a store-wide migration in one commit, not a flag, so
    the only useful moment to learn about it is well before the capture or
    sitting that would need it. The threshold is deliberately generous for
    that reason, and no ordinary store trips it.

    The two families differ in two ways that matter to the reader.

    RU is allocated PER SEGMENT, so each segment is its own wall and its own
    runway — a store may be comfortable overall and out of room in one domain.
    `activate` refuses at the ceiling rather than crossing it, so an RU store
    runs out safely.

    INT is not allocated at all — capture has no gate, so intents are ULIDs and
    have no ceiling. Only the DECIMAL ids an early store already carries have a
    wall, and it is much nearer. NOTHING refuses at it, because no verb owns an
    intent id, so a capture past it simply makes the store unloadable. What has
    changed is that the warning now has a fix to name: the next capture can be
    a ULID, and the two forms coexist permanently."""
    out = []

    spaces: dict[str | None, int] = {}
    for ru in store.rus():
        try:
            segment, number = ids.split(ru.id, "RU")
        except ValueError:
            continue                          # a draft: no sequence allocated
        spaces[segment] = max(spaces.get(segment, 0), number)
    for segment, highest in sorted(spaces.items(), key=lambda kv: kv[0] or ""):
        remaining = ids.SEQ_CEILING - highest
        if remaining > _HEADROOM_WARN:
            continue
        space = f"segment {segment}" if segment else "the unsegmented space"
        out.append(Finding(
            kind="id-headroom", severity="warning",
            message=(f"{remaining} id(s) left in {space}: the highest is "
                     f"{ids.format_id('RU', segment, highest)} and the "
                     f"{ids.SEQ_WIDTH}-character ceiling is "
                     f"{ids.format_id('RU', segment, ids.SEQ_CEILING)}."),
            suggestion="Allocate into another segment, or plan the width migration "
                       "before it is needed: the width is compiled into every schema "
                       "pattern, filename and cross-reference, so it changes "
                       "store-wide in ONE commit — every id renamed, every reference "
                       "rewritten, never mixed widths (formats §1). `rqunit activate` "
                       "refuses at the ceiling rather than crossing it, so this is "
                       "runway, not breakage."))

    # `max(decimal)` never decreases, so a store that TAKES this advice would
    # otherwise be warned identically forever — and `--strict` exits 1 on any
    # warning, making it a gate the documented remedy provably cannot clear.
    # One ULID capture is proof the store can proceed indefinitely, which is
    # the entire condition this warning exists to provoke.
    intents = [int(m.group(1)) for i in store.intents() if (m := _DECIMAL_INTENT.match(i))]
    escaped = any(_DECIMAL_INTENT.match(i) is None for i in store.intents())
    if intents and not escaped and ID_CEILING - max(intents) <= _HEADROOM_WARN:
        highest = max(intents)
        out.append(Finding(
            kind="id-headroom", severity="warning",
            message=(f"{ID_CEILING - highest} decimal INT id(s) left: the highest is "
                     f"INT-{highest:0{ID_WIDTH}d} and the {ID_WIDTH}-digit ceiling "
                     f"is INT-{ID_CEILING}."),
            suggestion="Capture the next intent as INT-<ULID>, which has no ceiling and "
                       "needs no coordination — that is the shape intents take now, and "
                       "the two forms coexist permanently, so nothing has to be renamed. "
                       "It matters because NOTHING allocates an intent id: no verb owns "
                       "them, so nothing refuses at this wall, and a capture past it "
                       "makes the store unloadable."))
    return out


def empty_store(store: Store) -> list[Finding]:
    """A store with no requirements, said out loud.

    `doctor` reported "store is structurally sound" on a freshly scaffolded
    store, which is true and useless: nothing is unsound because nothing is
    there. This is the wiring report, and having no requirements yet is the most
    load-bearing fact about a store on its first day.

    Keyed on "no RUs at all", never on a count — a note that fired below a
    threshold would pin point-in-time state and need re-tuning as the store
    grows. It stops the moment the first requirement lands, so it is a note a
    consumer can actually resolve, which is the test every doctor note has to
    pass."""
    if store.rus():
        return []
    return [Finding(
        kind="empty-store", severity="info",
        message="this store holds no requirements — every gate here is green "
                "because there is nothing to judge.",
        suggestion="Capture intent under spec/intent/, register the tags and actors your "
                   "requirements will use, then compile one draft per acceptance criterion "
                   "(§8.1). Structural soundness is not health while the store is empty.")]


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
            # No manifest, no judgment. This used to be silent too, on the
            # grounds that no consumer could point at one — an adapter shipped
            # only as source in this repository. That premise is gone: the
            # adapter is obtainable, so `manifest = "…"` is a fix a reader can
            # actually apply, and withholding the note now hides the fact that
            # a whole table of their configuration is unchecked.
            #
            # A first-party stack no longer reaches here at all: its manifest
            # ships in the pack and resolves with nothing wired. So this note
            # now addresses the case it is actually true of — a stack whose
            # adapter this build does not carry — and it must name where such a
            # manifest comes from. Naming the file without naming its source is
            # how the note used to terminate in a dead end, which reads as
            # actionable and is worse than saying nothing.
            #
            # Scoped to stacks that HAVE passthrough keys. A stack with none
            # loses nothing by having no manifest, and a note whose subject is
            # empty is the noise that teaches people to skim doctor.
            if stack.options:
                keys = ", ".join(sorted(stack.options)[:6])
                out.append(Finding(
                    kind="stack-config", severity="info",
                    message=(f"[stacks.{stack.name}] declares {len(stack.options)} "
                             f"adapter-owned key(s) that nothing validates ({keys}) — "
                             "no adapter manifest is wired."),
                    suggestion="Point `manifest = \"…\"` at the adapter.yaml that came "
                               "with this stack's adapter — it ships beside the adapter, "
                               "and a first-party adapter's is carried inside rqunit "
                               "itself and needs no wiring. It is the vocabulary authority "
                               "for this stack's passthrough keys, and core deliberately "
                               "never interprets them — so until one is wired, a typo "
                               "reads as configured and surfaces as the role that needed "
                               "the key behaving oddly."))
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
    return (empty_store(store) + lost_rus(store, root) + id_headroom(store)
            + orphan_artifacts(store) + dangling_reviews(store, root)
            + branch_staleness(root) + stack_config_health(root) + role_wiring(root))
