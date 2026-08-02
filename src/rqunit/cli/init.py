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

from ..schemas import SEED_DIR, SPEC_VERSION

# Every directory the loader reads, plus the ones the gates write into.
# Empty ones carry a .gitkeep: an absent directory and an empty one mean the
# same thing to the tools, but only one of them survives a clone.
STORE_DIRS = ("framework", "intent", "ru", "features", "manifests", "models",
              "gaps", "rationale", "reviews", "packets", "projections")

# Seed file → destination within spec/. Vocabularies and policy are consumer
# data (they are edited); schemas are not (they ship in the wheel).
SEEDS = {
    "tags.yaml": "framework",
    "actors.yaml": "framework",
    "coverage.policy.yaml": "framework",
    "conformance-exceptions.yaml": "framework",
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
# Missing keys fall back to conventional defaults; unknown keys are errors,
# because a typo silently ignored would read as configured.

[stacks.rust]
# Cargo.toml of every crate whose tests/ participate in verifies-tracing.
trace_scan = ["**/Cargo.toml"]
# Git pathspecs for the L14 new-test diff gate.
trace_diff = ["*/tests/*.rs"]
# tests/ directories swept by the hardcoded-bound advisory.
literal_scan = ["**/tests"]
# Crate receiving generated constants and statechart conformance suites.
conformance_crate = "spec-conformance-tests"
# Where this stack's extractor writes actual-surface.json ("" disables
# conformance reconciliation until an extractor is wired).
actual_surface = "spec-conformance-tests/actual-surface.json"
# Manifest service slug the extractor reports on. It does not guess this.
service = ""

# HTTP composition: which router function, in which file, mounts at what prefix
# under which access tier. This is a fact about THIS repository — not about
# Rust and not about a web framework — which is why it is configuration and not
# adapter code. Add one table per mounted router.
#
# [[stacks.rust.routers]]
# file = "http/src/routes/mod.rs"
# function = "router"
# prefix = "/api/v1/orders"
# access = "protected"

# Async surface: where subject constants are declared, and which sources
# publish them. Naming a subject is not the same as emitting one.
# [stacks.rust.messages]
# subject_sources = ["wire/src"]
# publisher_sources = ["adapters/nats/src"]
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


def _detect(root: Path) -> list[str]:
    return sorted({stack for marker, stack in MARKERS.items() if (root / marker).is_file()})


def _in_vcs(root: Path) -> bool:
    return any((candidate / ".git").exists() for candidate in [root, *root.parents])


@click.command()
@click.option("--store", "store_path", type=click.Path(path_type=Path), default=None,
              help="Where to create the store. Defaults to the current directory.")
@click.option("--stack", "stack_override", type=click.Choice(sorted(set(MARKERS.values()))),
              default=None, help="Skip detection and configure this stack.")
def main(store_path: Path | None, stack_override: str | None) -> None:
    """Scaffold a spec store: directories, seed vocabularies, coverage policy,
    the shared manifest, a pack pin, and rqunit.toml."""
    root = Path(store_path or Path.cwd()).resolve()
    spec = root / "spec"

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
    except OSError as e:
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
    if not _in_vcs(root):
        click.echo("  warning: not inside a git repository. The store is meant to travel "
                   "with the code it governs; commit it there.")
    click.echo("\nNext: capture intent in spec/intent/, register the tags and actors your "
               "requirements will use, then `rqunit lint`.")
