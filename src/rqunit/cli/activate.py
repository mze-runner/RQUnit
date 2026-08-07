"""`spec-activate` — Gate 1 activation tool (TASK-050/052, spec §7.1/§7.2).

Atomicity: all file mutations are computed in memory first, written together,
then staged and committed as ONE commit. Refuses to run while lints/checks are
red; refuses partial batches; refuses under-covered batch members (L21's
blocking-at-activation half); refuses mutating manifest edits without
--approve-impact (the §5.5 gate).

Concurrent allocation (documented, not "fixed"): two branch copies activating
independently allocate the SAME permanent ids from their own directory
listings; the collision surfaces at merge exactly as §7.1 designs — activation
is serialized through Gate 1 sittings, not through a counter file.

Crash injection for tests: SPEC_TOOLS_CRASH=post-rename aborts between the
renames and the cross-reference rewrite; acceptance is that nothing was
committed and the tree is restorable.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import click
import yaml

from ..canonical import canonical_hash, expected_fingerprints
from ..checks.base import run_checks
from ..errors import StoreError
from ..impact import build_report, diff_manifests, manifest_at_ref, render
from ..lints.base import run_lints
from ..lints.l21 import first_matching_rule, load_policy, violation_reason
from ..schemas import repo_root
from ..store import Store


@click.group()
def main() -> None:
    """Gate 1 activation tooling."""


def _validate_reviewer(reviewer: str) -> None:
    """Operator ids are stable HANDLES, never contact info (formats §9) —
    the store is published with the repository."""
    if "@" in reviewer:
        _fail(f"reviewer '{reviewer}' looks like contact info — use a stable handle "
              "(e.g. your VCS username); the store is published, emails never enter it (formats §9).")


@main.command()
@click.option("--store", "store_path", type=click.Path(path_type=Path), default=None)
@click.option("--feature", default=None, help="Activate every draft of this FEAT.")
@click.option("--drafts", multiple=True, help="Explicit draft ids (RU-draft-<ULID>).")
@click.option("--reviewer", required=True, help="Gate 1 reviewer id, recorded in the stamps.")
@click.option("--approve-impact", is_flag=True,
              help="Acknowledge the printed impact report for mutating manifest edits.")
@click.option("--no-commit", is_flag=True, help="Write files but skip the git commit (dry wiring).")
@click.option("--allow-stale-branch", is_flag=True,
              help="Activate anyway from a branch behind its upstream (accepts id-collision risk).")
def batch(store_path, feature, drafts, reviewer, approve_impact, no_commit,
          allow_stale_branch) -> None:
    _validate_reviewer(reviewer)
    root = store_path or repo_root()
    store = Store.load(root)

    # Ids come from the local directory listing (§7.1), so a branch behind its
    # upstream can allocate ids another branch already took. That staleness is
    # the ONLY precondition for a parallel-activation collision — refuse it
    # rather than partitioning the id space.
    if not allow_stale_branch:
        from ..doctor import branch_staleness
        for finding in branch_staleness(Path(root)):
            _fail(f"{finding.message} {finding.suggestion} "
                  "(--allow-stale-branch overrides.)")

    red = [v for v in run_lints(store) + run_checks(store) if v.severity == "error"]
    if red:
        for v in red[:10]:
            click.echo(f"  [{v.rule}] {v.artifact}: {v.message}", err=True)
        _fail(f"store is red ({len(red)} error(s), shown above) — activation refuses to run; "
              "fix or amend first.")

    all_drafts = {ru.id: ru for ru in store.rus() if ru.status == "draft"}
    if feature:
        members = [r for r in all_drafts.values() if r.raw.get("feature") == feature]
    elif drafts:
        missing = [d for d in drafts if d not in all_drafts]
        if missing:
            _fail(f"unknown draft(s): {', '.join(missing)} — batches are all-or-nothing.")
        members = [all_drafts[d] for d in drafts]
    else:
        _fail("nothing selected: pass --feature or --drafts.")
    if not members:
        _fail("empty batch — nothing to activate.")
    members.sort(key=lambda r: r.id)

    policy = load_policy(store)
    if policy:
        for ru in members:
            reason = violation_reason(first_matching_rule(policy, ru), ru.raw.get("verification") or [])
            if reason:
                _fail(f"{ru.id} violates coverage policy ({reason}) — a draft cannot activate under-covered (L21).")

    mutating = []
    for service, manifest in store.manifests().items():
        old = manifest_at_ref(root, "HEAD", service)
        if old is None:
            continue
        report = build_report(store, service, diff_manifests(old, manifest.raw))
        if report.changes:
            click.echo(render(report))
        mutating.extend(report.mutating)
    if mutating and not approve_impact:
        _fail("mutating manifest edit(s) present — re-run with --approve-impact after reviewing "
              "the report above (§5.5: a mutating edit without an impact report MUST NOT merge).")

    # ---- allocate ids from the directory listing (§7.1)
    ru_dir = Path(root) / "spec" / "ru"
    taken = [int(p.stem.split("-")[1]) for p in ru_dir.glob("RU-[0-9]*.yaml")]
    next_id = (max(taken) + 1) if taken else 1
    mapping = {ru.id: f"RU-{next_id + i:04d}" for i, ru in enumerate(members)}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # ---- compute every mutation in memory first
    writes: dict[Path, str] = {}
    deletes: list[Path] = []
    for ru in members:
        # Apply the id mapping to the member's OWN content first — stamps hash
        # the post-rewrite normative fields, otherwise the cross-ref rewrite
        # would invalidate the stamp it just received.
        raw = _remap(dict(ru.raw), mapping)
        new_id = mapping[ru.id]
        raw["id"] = new_id
        raw["draft_id"] = ru.id
        raw["status"] = "active"
        raw["gate1_stamp"] = {"hash": "", "by": reviewer, "at": now}
        fingerprints = expected_fingerprints(store, raw)
        if fingerprints:
            raw["link_fingerprints"] = fingerprints
        raw["gate1_stamp"]["hash"] = canonical_hash(raw)
        writes[ru_dir / f"{new_id}.yaml"] = yaml.safe_dump(raw, sort_keys=False, allow_unicode=True)
        deletes.append(ru.path)
        target_id = raw.get("supersedes")
        if target_id:
            target = next((r for r in store.rus() if r.id == target_id), None)
            if target and target.status == "active":
                traw = dict(target.raw)
                traw["status"] = "superseded"
                writes[target.path] = yaml.safe_dump(traw, sort_keys=False, allow_unicode=True)

    # ---- SIMULATE the post-activation store BEFORE touching the real tree.
    # The pre-flight above checked the PRE-activation store, where C1/C2/C3
    # deliberately skip drafts — anything true only after the status flip
    # would otherwise surface at the commit gate, after files were written
    # (reproduced live at the first real Gate 1 sitting).
    sim_root = Path(tempfile.mkdtemp(prefix="spec-activate-sim-"))
    try:
        shutil.copytree(Path(root) / "spec", sim_root / "spec")
        _apply_mutations(sim_root, Path(root), writes, deletes)
        _rewrite_tree(sim_root / "spec", mapping)
        sim_store = Store.load(sim_root)
        sim_red = [v for v in run_lints(sim_store) + run_checks(sim_store)
                   if v.severity == "error"]
        if sim_red:
            for v in sim_red[:10]:
                click.echo(f"  [{v.rule}] {v.artifact}: {v.message}", err=True)
            _fail(f"simulated POST-activation store is red ({len(sim_red)} error(s), shown "
                  "above) — nothing was written; amend the batch and re-run.")
    finally:
        shutil.rmtree(sim_root, ignore_errors=True)

    # Pre-flight the emitter BEFORE any mutation: targets() now execs a
    # declared adapter, and an unbuilt binary or a stale artifact response
    # must fail here — with nothing written — rather than inside the
    # mutated-tree window. The census it validates is (model, check id),
    # which activation's renames never change, so a clean pre-flight is a
    # clean regeneration later.
    from ..generate import targets, write_all
    try:
        targets(Store.load(root), Path(root))
    except StoreError as e:
        _fail(f"the emitter pre-flight failed — nothing was written: {e}")

    # ---- rename phase (real tree) — every mutated path is journaled so a
    # refused commit rolls the operation back instead of stranding it.
    journal: dict[Path, str | None] = {}
    for path in list(writes) + deletes:
        journal[path] = path.read_text() if path.exists() else None
    for path, content in writes.items():
        path.write_text(content)
    for path in deletes:
        path.unlink()
    if os.environ.get("SPEC_TOOLS_CRASH") == "post-rename":
        _fail("injected crash between rename and rewrite (test hook) — no commit was made; "
              "the working tree is restorable via git.")

    # ---- cross-reference rewrite phase (same invocation — splitting is FORBIDDEN, §7.1)
    for path, before in _rewrite_tree(Path(root) / "spec", mapping):
        journal.setdefault(path, before)

    # Regenerate projections/conformance artifacts BEFORE the commit: a
    # pre-commit `spec-generate check` gate must see them current, not stale
    # against the just-renamed RUs. The emitter was pre-flighted above; if it
    # still fails here, the journal restores every mutated file.
    post = Store.load(root)
    try:
        for path in targets(post, Path(root)):
            journal.setdefault(path, path.read_text() if path.exists() else None)
        regenerated = write_all(post, Path(root))
    except StoreError as e:
        _restore(journal)
        _fail("regeneration failed after the rename phase — ALL written files were "
              f"rolled back; the store is exactly as before this run: {e}")

    if not no_commit:
        try:
            subprocess.run(["git", "-C", str(root), "add", "spec"], check=True)
            for path in regenerated:
                subprocess.run(["git", "-C", str(root), "add", str(path)], check=True)
            ids = ", ".join(mapping.values())
            subprocess.run(["git", "-C", str(root), "commit", "-m",
                            f"spec: activate {ids} (Gate 1, reviewer {reviewer})"],
                           check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            _restore(journal)
            subprocess.run(["git", "-C", str(root), "reset", "-q", "HEAD", "--", "."],
                           check=False, capture_output=True)
            detail = ((e.stderr or "") + (e.stdout or "")).strip()
            _fail("the commit gate refused the activation — ALL written files were rolled "
                  f"back; the store is exactly as before this run. Gate output:\n{detail[-2000:]}")
    for old_id, new_id in mapping.items():
        click.echo(f"{old_id} -> {new_id}")


@main.command()
@click.option("--store", "store_path", type=click.Path(path_type=Path), default=None)
@click.option("--reviewer", required=True)
def restamp(store_path, reviewer) -> None:
    """Write gate1_stamps for active RUs missing them — the re-validation path
    for manual activations (plan D-P4.5) and for human re-affirmation of
    suspect links (refreshes fingerprints under the reviewer's id)."""
    _validate_reviewer(reviewer)
    root = store_path or repo_root()
    store = Store.load(root)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    stamped = 0
    for ru in store.rus():
        if ru.status != "active":
            continue
        raw = dict(ru.raw)
        changed = False
        if "gate1_stamp" not in raw:
            raw["gate1_stamp"] = {"hash": canonical_hash(raw), "by": reviewer, "at": now}
            changed = True
        current = expected_fingerprints(store, raw)
        if current != (raw.get("link_fingerprints") or {}):
            if current:
                raw["link_fingerprints"] = current
            else:
                raw.pop("link_fingerprints", None)
            changed = True
        if changed:
            ru.path.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True))
            stamped += 1
    click.echo(f"stamped/refreshed {stamped} RU(s) under reviewer {reviewer}")


@main.command()
@click.option("--store", "store_path", type=click.Path(path_type=Path), default=None)
@click.option("--model", "model_ref", required=True,
              help="Model id (MDL-<id> or bare) whose active dependents to re-affirm.")
@click.option("--ru", "ru_ids", multiple=True,
              help="Limit to these RU ids (the subset kept when others get superseded instead).")
@click.option("--reviewer", required=True)
def reaffirm(store_path, model_ref, ru_ids, reviewer) -> None:
    """Gate 1 re-affirmation after a model edit — the lawful model-evolution
    path (GAP22): for every ACTIVE RU whose verification pins the model with
    a stale hash, update model_hash to the current model, re-stamp under the
    reviewer's id, refresh fingerprints, and regenerate projections and
    conformance. Judgment stays human: an RU whose MEANING the model change
    alters must be superseded instead — the printed statements are the
    sitting's reading material. Prior Gate 2 records stop counting (they
    predate the new stamp). Writes files only — review the diff and commit."""
    _validate_reviewer(reviewer)
    root = store_path or repo_root()
    store = Store.load(root)
    bare = model_ref.removeprefix("MDL-")
    model = store.models().get(bare)
    if model is None:
        _fail(f"MDL-{bare} does not exist in the store.")
    # Pre-flight BEFORE any write: this verb runs immediately after a model
    # edit, which is exactly when a dialect violation is most likely, and
    # re-stamping RUs against a model that cannot render would leave the
    # store half-mutated.
    _require_renderable(store, bare)
    known = {ru.id for ru in store.rus()}
    unknown = [r for r in ru_ids if r not in known]
    if unknown:
        _fail(f"unknown RU id(s): {', '.join(unknown)}")

    def stale_entries(ru):
        return [e for e in ru.raw.get("verification") or []
                if e.get("type") == "model" and e["ref"].removeprefix("MDL-") == bare
                and e["model_hash"] != model.content_hash]

    affected = [ru for ru in store.rus()
                if ru.status == "active"
                and (not ru_ids or ru.id in ru_ids)
                and stale_entries(ru)]
    if not affected:
        click.echo("nothing to re-affirm — no active RU pins a stale hash for this model.")
        return
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for ru in affected:
        raw = dict(ru.raw)
        for entry in stale_entries(ru):
            entry["model_hash"] = model.content_hash
        raw["gate1_stamp"] = {"hash": canonical_hash(raw), "by": reviewer, "at": now}
        fingerprints = expected_fingerprints(store, raw)
        if fingerprints:
            raw["link_fingerprints"] = fingerprints
        else:
            raw.pop("link_fingerprints", None)
        ru.path.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True))
        click.echo(f"re-affirmed {ru.id}: {' '.join(raw['statement'].split())}")
    from ..generate import write_all
    write_all(Store.load(root), Path(root))
    click.echo(f"{len(affected)} RU(s) re-stamped under {reviewer} against MDL-{bare} "
               f"@ {model.content_hash[:19]}…; projections/conformance regenerated. "
               "Prior Gate 2 records for these RUs no longer count. Review the diff and commit.")


@main.command()
@click.argument("pairs", nargs=-1, required=True, metavar="[RU-XXXX=REF]...")
@click.option("--store", "store_path", type=click.Path(path_type=Path), default=None)
@click.option("--match", "match_text", default=None,
              help="Substring selecting ONE TODO description when an RU carries several of the target's type.")
@click.option("--reviewer", required=True)
def resolve(pairs, store_path, match_text, reviewer) -> None:
    """Gate 1 TODO resolution — the debt-conversion path: replace a TODO(…)
    verification entry on an ACTIVE RU with a real, resolvable ref of the
    SAME type (a scanned test id), re-stamp under the
    reviewer's id, refresh fingerprints, regenerate. Strictly strengthening:
    statement/scope/tier untouched, entries never removed, real refs never
    replaced — anything else stays supersession-only. Prior Gate 2 records
    stop counting (they predate the new stamp). Writes files only — review
    the diff and commit."""
    _validate_reviewer(reviewer)
    root = store_path or repo_root()
    store = Store.load(root)
    _require_renderable(store)     # regeneration is this verb's last act
    by_id = {ru.id: ru for ru in store.rus()}

    test_ids: set[str] | None = None  # scanned lazily, only if a test target appears
    plan: list[tuple[object, dict, str]] = []  # (ru, entry, target)
    for pair in pairs:
        ru_id, sep, target = pair.partition("=")
        if not sep or not target:
            _fail(f"'{pair}' is not RU-XXXX=REF.")
        ru = by_id.get(ru_id)
        if ru is None:
            _fail(f"{ru_id} does not exist in the store.")
        if ru.status != "active":
            _fail(f"{ru_id} is {ru.status} — TODO resolution re-stamps ACTIVE RUs; "
                  "drafts are simply edited before activation.")
        if target.startswith("MDL-"):
            _fail(f"{ru_id}: model refs carry hash+conformance fields — resolve those by "
                  "regenerating conformance, not through this verb.")
        entry_type = "test"
        if test_ids is None:
            from ..trace import scan_tests
            test_ids = {c.id for c in scan_tests(root)}
        if target not in test_ids:
            _fail(f"{ru_id}: test id '{target}' resolves to no scanned test. "
                  "A TODO converts only to a check that EXISTS.")
        candidates = [e for e in ru.raw.get("verification") or []
                      if e.get("type") == entry_type
                      and str(e.get("ref", "")).startswith("TODO(")
                      and (match_text is None or match_text in e["ref"])]
        if not candidates:
            _fail(f"{ru_id} has no {entry_type}-type TODO entries"
                  + (f" matching '{match_text}'" if match_text else "")
                  + " — real refs are never replaced here (change = supersession).")
        if len(candidates) > 1:
            listing = "\n".join(f"  {i + 1}. {e['ref']}" for i, e in enumerate(candidates))
            _fail(f"{ru_id} has {len(candidates)} {entry_type}-type TODO entries — ambiguous:\n"
                  f"{listing}\nre-run with --match <substring> to select one "
                  "(identical descriptions are an authoring bug — clean the RU by supersession).")
        plan.append((ru, candidates[0], target))

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for ru, entry, target in plan:
        raw = dict(ru.raw)
        before = entry["ref"]
        entry["ref"] = target
        raw["gate1_stamp"] = {"hash": canonical_hash(raw), "by": reviewer, "at": now}
        fingerprints = expected_fingerprints(store, raw)
        if fingerprints:
            raw["link_fingerprints"] = fingerprints
        else:
            raw.pop("link_fingerprints", None)
        ru.path.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True))
        click.echo(f"resolved {ru.id}: {before} -> {target}")
    from ..generate import write_all
    write_all(Store.load(root), Path(root))
    click.echo(f"{len(plan)} TODO(s) resolved and re-stamped under {reviewer}; "
               "projections regenerated. Prior Gate 2 records for these RUs no "
               "longer count. Review the diff and commit.")


def _apply_mutations(sim_root: Path, real_root: Path,
                     writes: dict[Path, str], deletes: list[Path]) -> None:
    """Replay the computed mutations onto the simulation copy."""
    for path, content in writes.items():
        target = sim_root / path.relative_to(real_root)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    for path in deletes:
        target = sim_root / path.relative_to(real_root)
        if target.exists():
            target.unlink()


def _rewrite_tree(spec_dir: Path, mapping: dict[str, str]) -> list[tuple[Path, str]]:
    """Rewrite draft ids to permanent ids across the tree (draft_id provenance
    lines exempt). Returns (path, original_text) for every file changed."""
    changed: list[tuple[Path, str]] = []
    for path in spec_dir.rglob("*.yaml"):
        text = path.read_text()
        replaced = text
        for old_id, new_id in mapping.items():
            replaced = "\n".join(
                line if line.startswith("draft_id:") else line.replace(old_id, new_id)
                for line in replaced.splitlines()
            ) + ("\n" if replaced.endswith("\n") else "")
        if replaced != text:
            changed.append((path, text))
            path.write_text(replaced)
    return changed


def _remap(value, mapping: dict[str, str]):
    """Recursively replace draft ids with their permanent ids in an artifact's
    own content (statements, refs — everything except the draft_id field,
    which is set afterward and keeps the ULID)."""
    if isinstance(value, str):
        for old_id, new_id in mapping.items():
            value = value.replace(old_id, new_id)
        return value
    if isinstance(value, list):
        return [_remap(v, mapping) for v in value]
    if isinstance(value, dict):
        return {k: _remap(v, mapping) for k, v in value.items()}
    return value


def _require_renderable(store: Store, model_id: str | None = None) -> None:
    """Refuse before writing anything when a model cannot render. Every verb
    here regenerates projections as its last act; discovering the refusal
    then would strand a half-written store."""
    from ..model_rules import require_sound
    try:
        for candidate in ([model_id] if model_id else store.models()):
            require_sound(store, candidate)
    except StoreError as e:
        _fail(f"nothing was written — {e}")


def _restore(journal: dict[Path, str | None]) -> None:
    """Put every journaled file back exactly as it was before this run."""
    for path, before in journal.items():
        if before is None:
            path.unlink(missing_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(before)


def _fail(message: str) -> None:
    click.echo(f"spec-activate: {message}", err=True)
    sys.exit(1)
