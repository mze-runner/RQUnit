"""`spec-lint` — runs lints L1–L18 over a store (formats §4 report contract)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from ..config import load as load_config, retired_key_uses
from ..errors import BadConfig, StoreError
from ..lints.base import run_lints
from ..schemas import repo_root
from ..store import Store
from ..violations import Violation, build_report, exit_code, render_text, schema_violation


@click.command()
@click.option("--store", "store_path", type=click.Path(path_type=Path), default=None,
              help="Store root (directory containing spec/). Defaults to the repo root.")
@click.option("--only", default=None, help="Run a single lint, e.g. --only L3.")
@click.option("--format", "fmt", type=click.Choice(["json", "text"]), default="json")
@click.option("--strict", is_flag=True, help="Warnings also fail the run.")
def main(store_path: Path | None, only: str | None, fmt: str, strict: bool) -> None:
    try:
        root = store_path or repo_root()
    except FileNotFoundError as e:
        click.echo(str(e), err=True)
        sys.exit(2)
    try:
        # rqunit.toml is part of the store's health, and lint is the verb that
        # runs on every edit and in every pre-commit hook — so this is where a
        # config that cannot be read has to surface. It used to surface nowhere
        # a consumer looks: only `trace` loaded the config, and it reported the
        # failure as a TOOL error, so lint, check and doctor all exited 0 over a
        # repository whose configuration the loader rejects outright.
        config = load_config(root)
        store = Store.load(root)
        violations = run_lints(store, only=only)
        # A retired key still sitting where core used to read it configures
        # nothing, and looks exactly like live adapter passthrough. Core cannot
        # judge an unknown key — but it can recognise one it used to own.
        violations += [
            Violation(
                rule="CONFIG", severity="warning", artifact="rqunit.toml",
                path="rqunit.toml",
                message=(f"[stacks.{stack}] {key} is retired — core no longer reads it, "
                         "so it sits in adapter passthrough configuring nothing."),
                # The instruction comes from the key, whole. Retirement has two
                # shapes and one template phrasing cannot serve both.
                suggestion=f"{instruction} While it stays, the file claims a setting "
                           "the tool does not have.")
            for stack, key, instruction in retired_key_uses(config)
        ]
        checked = (len(store.rus()) + len(store.features()) + len(store.gaps())
                   + len(store.manifests()) + len(store.models()) + len(store.intents()))
    except BadConfig as e:
        # A violation, never a tool error — the same rule DialectViolation
        # states: one fact must not read as "rqunit is broken" on one command
        # and "your store is wrong" on another.
        where = e.path or str(root / "rqunit.toml")
        violations = [Violation(
            rule="CONFIG", severity="error", artifact="rqunit.toml",
            # StoreError prefixes its own path; the report already carries one,
            # and printing it twice reads as two different files.
            path=where, message=str(e).removeprefix(f"{where}: "),
            suggestion="Fix rqunit.toml before anything else — a config the loader "
                       "rejects means every adapter role is unavailable, so trace and "
                       "conformance observe nothing (§12.1). Core reads a closed key set "
                       "per stack; everything else is adapter-owned passthrough, checked "
                       "against that adapter's manifest.",
        )]
        checked = 0
    except StoreError as e:
        # A store that cannot load is itself the finding (schema stage red),
        # not a tool error.
        violations = [schema_violation(e, root)]
        checked = 0
    except Exception as e:  # tool failure — exit 2 per the CLI contract
        click.echo(f"spec-lint: tool error: {e}", err=True)
        sys.exit(2)
    report = build_report("spec-lint", violations, checked, root)
    if only in (None, "L20"):
        _write_suspect_queue(root, [v for v in violations if v.rule == "L20"])
    click.echo(json.dumps(report, indent=2) if fmt == "json" else render_text(report))
    sys.exit(exit_code(report, strict=strict))


def _write_suspect_queue(root: Path, findings) -> None:
    """spec/projections/suspect-queue.json (TASK-052, plan D-P4.4): refreshed
    when L20 findings exist, emptied when none. Entries only — no timestamp,
    so an unchanged queue produces no diff noise."""
    path = Path(root) / "spec" / "projections" / "suspect-queue.json"
    entries = [{"ru": v.artifact, "message": v.message} for v in findings]
    payload = json.dumps({"suspect": entries}, indent=2) + "\n"
    if not path.parent.is_dir():
        return  # not a full store (fixture subsets) — nothing to project
    if not path.exists() or path.read_text() != payload:
        path.write_text(payload)
