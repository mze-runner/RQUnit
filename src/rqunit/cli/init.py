"""`rqunit init` — scaffold a store in a consumer repository.

The only verb that writes into an *empty* repository, and therefore the only
one that must decide nothing: the store layout is fixed by spec §12.1, so
this is a copy, not a generator. Seeds come from the pack that ships with the
tool, which is why a fresh store is always consistent with the version
enforcing it.

Deliberately asks nothing. The store root is fixed; reviewer identity is
per-sitting and never configuration; vocabularies start empty because a
seeded taxonomy nobody chose is the fastest way to a taxonomy nobody obeys.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import click

from ..errors import StoreError
from ..schemas import SEED_DIR, SPEC_VERSION

# Agent-runtime templates, emitted into the consumer's own runtime directory.
# They ship here rather than in the handbook because guidance nobody installs
# is guidance that drifts: these files describe the CURRENT vocabulary, and a
# consumer holding a hand-copied edition of them is holding whatever the
# vocabulary was on the day they copied it.
INTEGRATIONS = {
    "claude-code": ".claude",
}

# Every directory the loader reads, plus the ones the gates write into.
# Empty ones carry a .gitkeep: an absent directory and an empty one mean the
# same thing to the tools, but only one of them survives a clone.
STORE_DIRS = ("framework", "intent", "ru", "features", "manifests", "models",
              "gaps", "rationale", "reviews", "packets", "projections",
              "check-evidence")

# Seed file → destination within spec/. Vocabularies and policy are consumer
# data (they are edited); schemas are not (they ship in the wheel).
SEEDS = {
    "tags.yaml": "framework",
    "actors.yaml": "framework",
    "coverage.policy.yaml": "framework",
    "conformance-exceptions.yaml": "framework",
    "shims.yaml": "framework",
    "shared.manifest.yaml": "manifests",
}

# Marker file → stack name. Detection is reported, never enforced: a wrong
# guess must cost the operator one flag, not a broken store.
MARKERS = {
    "Cargo.toml": "rust",
    "pom.xml": "jvm",
    "build.gradle": "jvm",
    "build.gradle.kts": "jvm",
    "package.json": "node",
    "pyproject.toml": "python",
}

RUST_CONFIG = """\
# RQUnit consumer configuration. Only repo-specific inputs belong here — the
# store layout itself is fixed (spec/ at this root) and is never configured.
#
# Any [stacks.<name>] table declares a stack. Core interprets only the
# `adapter` role declarations and `literal_scan`; every other key under a
# stack is the adapter's own configuration, passed through untouched. Typos in
# core-read keys are errors, because a typo silently ignored would read as
# configured; passthrough keys are checked against the adapter's manifest.

[stacks.rust]

# tests/ directories swept by the hardcoded-bound advisory (core-read).
literal_scan = ["**/tests"]

# ---- adapter-owned configuration ---------------------------------------------
# Core passes everything from here to the adapter table through untouched; the
# Rust adapter reads it. Each entry is a fact about THIS repository — not
# about Rust, and not about any framework. An extractor that guessed would
# report a surface nobody declared, and the reconciler would believe it.
# Leave a section out and that family is simply not examined, which the
# report says out loud rather than passing quietly.

# Cargo.toml of every crate whose tests/ the scanner walks (read by the
# scan-checks binary when it runs over this tree).
trace_scan = ["**/Cargo.toml"]
# Crate receiving generated constants and statechart conformance suites.
conformance_crate = "spec-conformance-tests"
# Manifest service slug the extractor reports on. It does not guess this.
service = ""

# ---- adapter roles -----------------------------------------------------------
# Each role is either a command core execs (cmd = ["..."], argv, no shell) or
# an artifact an earlier pipeline step produced (artifact = "path"). A role
# left undeclared is unavailable — reported as such, never silently skipped.

[stacks.rust.adapter]
# Where this stack's extractor writes actual-surface.json — the artifact
# `rqunit conformance` reconciles against the manifests.
extractor = { artifact = "spec-conformance-tests/actual-surface.json" }
# The scanner feeds `rqunit trace` (traceability + the L14 new-test gate).
# Build the adapter in its own toolchain, or produce the artifact in your
# pipeline and declare artifact = "path" instead. In artifact mode L14 judges
# the artifact, not your sources — regenerate it in the same pipeline step
# that runs the gate.
# scanner = { cmd = ["adapters/rust/target/release/scan-checks"] }
# emitter = { cmd = ["adapters/rust/target/release/emit-suite"] }
# The off-ramp. `rqunit trace --strip` removes the trace annotations adoption
# asked you to write into your own tests — the orphaned ones by default, all of
# them with --all. Declare it and off-boarding is one command; leave it out and
# this stack can be adopted but not un-adopted, which the strip run says out
# loud rather than reporting a sweep it never performed. cmd only: a stripper
# answers a request computed from today's store, so no committed artifact can
# be that answer.
# stripper = { cmd = ["adapters/rust/target/release/strip-annotations"] }
# The evidence probe reads your runner's output and reports which checks
# passed and which failed; `rqunit evidence record` folds a run into the
# ledger. Without it nothing can tell a check that has demonstrated it can
# fail from one that has only ever been green (L26).
# evidence = { artifact = "spec-conformance-tests/check-evidence.json" }
# The adapter's manifest, declaring its roles and the config keys it reads.
# manifest = "adapters/rust/adapter.yaml"

# HTTP composition: which router function, in which file, mounts at what prefix
# under which access tier. One table per mounted router.
#
# [[stacks.rust.routers]]
# file = "http/src/routes/mod.rs"
# function = "router"
# prefix = "/api/v1/orders"
# access = "protected"

# Async surface: where subject constants are declared, and which sources
# publish them. Naming a subject is not the same as emitting one.
#
# [stacks.rust.messages]
# subject_sources = ["wire/src"]
# publisher_sources = ["adapters/nats/src"]

# Audit: where audit-code constants are declared, and which sources record
# them. Declaring a code is not recording one — which is exactly what CF10
# checks, and it can only check it if you point it at both.
#
# [stacks.rust.audit]
# code_sources = ["telemetry/src"]
# emitter_sources = ["application/src"]
"""

BARE_CONFIG = """\
# RQUnit consumer configuration. Only repo-specific inputs belong here — the
# store layout itself is fixed (spec/ at this root) and is never configured.
# Missing keys fall back to conventional defaults; unknown keys are errors.
#
# No [stacks] table yet: store-scoped verification (lint, check, doctor,
# report, the gates) needs none. Trace scanning and manifest/code conformance
# come online when this stack has an adapter.
"""

PACK_PIN = """\
# The RQUnit SPECIFICATION version this store was authored against — the
# vocabulary its manifests and RUs are written in. Not the tool version: a tool
# fix changes no vocabulary, and the two move independently on purpose.
# Tooling reports this; the store is not rewritten when the tool moves ahead.
pack: "{version}"
"""


INTEGRATION_DIR = Path(__file__).parent.parent / "integrations"


def emit_integrations(root: Path, overwrite: bool) -> tuple[list[str], list[str]]:
    """Copy the agent-runtime templates into the consumer repository.

    Returns (written, skipped) as repo-relative paths. Without `overwrite` an
    existing file is never touched: these land in a directory the consumer also
    authors in, and a scaffold that silently replaces someone's edited hook is
    a scaffold nobody runs twice.
    """
    written, skipped = [], []
    for source_name, destination_name in INTEGRATIONS.items():
        source = INTEGRATION_DIR / source_name
        if not source.is_dir():
            continue
        for path in sorted(source.rglob("*")):
            if not path.is_file():
                continue
            target = root / destination_name / path.relative_to(source)
            relative = str(target.relative_to(root))
            if target.exists() and not overwrite:
                skipped.append(relative)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            # copy2 rather than copyfile: the hooks are executed by the agent
            # runtime, and a hook that arrives without its executable bit fails
            # in a way that looks like the guard passing.
            shutil.copy2(path, target)
            written.append(relative)
    return written, skipped


def _detect(root: Path) -> list[str]:
    return sorted({stack for marker, stack in MARKERS.items() if (root / marker).is_file()})


def _in_vcs(root: Path) -> bool:
    return any((candidate / ".git").exists() for candidate in [root, *root.parents])


@click.command()
@click.option("--store", "store_path", type=click.Path(path_type=Path), default=None,
              help="Where to create the store. Defaults to the current directory.")
@click.option("--stack", "stack_override", type=click.Choice(sorted(set(MARKERS.values()))),
              default=None, help="Skip detection and configure this stack.")
@click.option("--refresh-integrations", is_flag=True,
              help="Rewrite the agent-runtime templates in place and touch nothing else. "
                   "The upgrade path: they teach the vocabulary, so a store on a newer tool "
                   "with older templates is being taught the wrong one.")
def main(store_path: Path | None, stack_override: str | None,
         refresh_integrations: bool) -> None:
    """Scaffold a spec store: directories, seed vocabularies, coverage policy,
    the shared manifest, a pack pin, rqunit.toml, and the agent-runtime
    templates."""
    root = Path(store_path or Path.cwd()).resolve()
    spec = root / "spec"

    if refresh_integrations:
        try:
            written, _ = emit_integrations(root, overwrite=True)
        except OSError as e:
            click.echo(f"rqunit init: tool error: {e}", err=True)
            sys.exit(2)
        click.echo(f"rqunit init · refreshed {len(written)} template(s) under {root}")
        for name in written:
            click.echo(f"  {name}")
        click.echo("\nLocal edits to these files were overwritten — that is what --refresh-"
                   "integrations means. Re-apply them, or keep them somewhere the refresh "
                   "does not reach.")
        return

    if spec.exists() and any(spec.iterdir()):
        click.echo(f"rqunit init: {spec} already exists and is not empty — refusing to "
                   "write into it.\n"
                   "    A store is scaffolded once. To add what a partial store is "
                   "missing, create the directory or copy the seed by hand.", err=True)
        sys.exit(1)

    try:
        for name in STORE_DIRS:
            (spec / name).mkdir(parents=True, exist_ok=True)
        for name, destination in SEEDS.items():
            shutil.copyfile(SEED_DIR / name, spec / destination / name)
        (spec / "framework" / "pack.yaml").write_text(
            PACK_PIN.format(version=SPEC_VERSION))
        for name in STORE_DIRS:
            directory = spec / name
            if not any(directory.iterdir()):
                (directory / ".gitkeep").touch()

        stacks = [stack_override] if stack_override else _detect(root)
        config = root / "rqunit.toml"
        wrote_config = not config.exists()
        if wrote_config:
            config.write_text(RUST_CONFIG if "rust" in stacks else BARE_CONFIG)
        emitted, kept = emit_integrations(root, overwrite=False)
        # Generate before handing the store over. Projections are committed and
        # currency-checked, so a store that has never generated is REPORTED as
        # out of date — which made a freshly scaffolded store fail its own gate
        # on the first commit, for a reason the operator did nothing to cause.
        # A scaffold whose next gate is red is a scaffold that teaches people
        # the gate is noise.
        from ..generate import write_all
        from ..store import Store
        generated = write_all(Store.load(root), root)
    except (OSError, StoreError) as e:
        click.echo(f"rqunit init: tool error: {e}", err=True)
        sys.exit(2)

    click.echo(f"rqunit init · store created at {spec}")
    if stack_override:
        click.echo(f"  stack: {stack_override} (from --stack)")
    elif stacks:
        click.echo(f"  detected: {', '.join(stacks)}")
    else:
        click.echo("  detected: no build manifest at this root")
    if stacks and "rust" not in stacks:
        click.echo(f"  no adapter ships for {'/'.join(stacks)} yet, so rqunit.toml carries "
                   "no [stacks] table — store verification and both gates work regardless.")
    if not wrote_config:
        click.echo("  rqunit.toml already existed — left untouched.")
    if emitted:
        click.echo(f"  agent templates: {len(emitted)} written under .claude/ "
                   "(skills, agents, hooks). The hooks are inert until a packet is armed; "
                   "wire them with .claude/settings-hook-snippet.jsonc.")
    if kept:
        click.echo(f"  agent templates: {len(kept)} already existed — left untouched. "
                   "`rqunit init --refresh-integrations` overwrites them.")
    click.echo(f"  projections: {len(generated)} generated — commit them with the store; "
               "they are currency-checked, never hand-edited.")
    if not _in_vcs(root):
        click.echo("  warning: not inside a git repository. The store is meant to travel "
                   "with the code it governs; commit it there.")
    click.echo("\nNext: capture intent in spec/intent/, register the tags and actors your "
               "requirements will use, then `rqunit lint`.")
