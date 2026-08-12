"""`rqunit conformance` — reconcile manifests against what the code exposes.

Reads adapter observations. Artifact mode reads a file the stack's own
pipeline produced; cmd mode execs a declared, prebuilt adapter as an opaque
black box behind the pinned schema. Either way this toolchain never invokes
a language toolchain or build system — building the adapter is the
consumer's job, in the stack's own build.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from ..conformance import boundary_provenance, load_actual, reject_exceptions
from ..conformance import run as run_conformance
from ..config import load as load_config
from ..errors import BadConfig, StoreError
from ..invoke import run_role
from ..schemas import repo_root
from ..store import Store
from ..violations import build_report, exit_code, render_text


@click.command()
@click.option("--store", "store_path", type=click.Path(path_type=Path), default=None,
              help="Store root (directory containing spec/). Defaults to the repo root.")
@click.option("--artifact", "artifacts", multiple=True, type=click.Path(path_type=Path),
              help="actual-surface artifact(s); defaults to every configured stack's.")
@click.option("--format", "fmt", type=click.Choice(["json", "text"]), default="json")
@click.option("--strict", is_flag=True, help="Findings also fail the run.")
def main(store_path: Path | None, artifacts: tuple[Path, ...], fmt: str, strict: bool) -> None:
    """Report CF1–CF11 divergences between the manifests and the code."""
    try:
        root = Path(store_path or repo_root())
        store = Store.load(root)
        if artifacts:
            loaded = [load_actual(Path(a)) for a in artifacts]
        else:
            loaded = _from_config(root)
        if not loaded:
            click.echo("rqunit conformance: no extractor configured "
                       "([stacks.<name>.adapter] extractor = { cmd = [...] } or "
                       "{ artifact = \"...\" } in rqunit.toml)", err=True)
            sys.exit(2)
        violations = run_conformance(store, root, loaded)
        # What extraction actually reached. The manifest is allowed to exceed
        # what an extractor can see — that is how it carries target state — so
        # the unproven fraction has to be countable, or a green run reads as
        # "checked" when most of the boundary was never looked at (§5.6).
        provenance = boundary_provenance(store, loaded)
    except BadConfig as e:
        # Same rule as `lint` and `trace`: a rejected config is the store
        # being wrong, not the tool breaking. One fact, one category, every
        # surface.
        click.echo(f"ERROR CONFIG {e}", err=True)
        click.echo("    Fix rqunit.toml, then re-run. `rqunit lint` reports this "
                   "with the full rule reference.", err=True)
        sys.exit(1)
    except StoreError as e:
        click.echo(f"rqunit conformance: {e}", err=True)
        sys.exit(2)
    except Exception as e:
        click.echo(f"rqunit conformance: tool error: {e}", err=True)
        sys.exit(2)

    report = build_report("rqunit-conformance", violations, len(loaded), root)
    report["boundary"] = provenance
    if fmt == "json":
        click.echo(json.dumps(report, indent=2))
    else:
        click.echo(render_text(report))
        click.echo(
            f"\nBoundary: {provenance['endpoints']} endpoint(s), "
            f"{provenance['shapes_declared']} shape(s) declared — "
            f"{provenance['fields_extractor_confirmed']} field(s) extractor-confirmed, "
            f"{provenance['fields_unproven_by_extraction']} not reached by extraction "
            "(test-proved or unproven).")
    sys.exit(exit_code(report, strict=strict))


def _from_config(root: Path) -> list[dict]:
    """Every declared extractor's observation, through the one invocation
    door — artifact mode reads the file the pipeline produced, cmd mode execs
    the declared adapter; same contract and same checks either way. Each
    observation is tagged with the place an operator can act on, so a
    divergence from one probe is never attributed to another's file."""
    config = load_config(root)
    loaded = []
    for stack in config.stacks:
        role = stack.adapter.extractor
        if role is None:
            continue
        where = (str(root / role.artifact) if role.artifact
                 else f"[stacks.{stack.name}.adapter] extractor")
        data = run_role(root, stack, "extractor", schema="actual-surface.schema.json")
        reject_exceptions(data, where)
        data["_source"] = where
        loaded.append(data)
    return loaded
