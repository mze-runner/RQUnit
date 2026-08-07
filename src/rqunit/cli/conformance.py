"""`rqunit conformance` — reconcile manifests against what the code exposes.

Reads adapter artifacts; never runs an extractor. Extraction belongs to the
stack's own build system (cargo test, gradle, npm test), which keeps this
toolchain free of every language toolchain it governs.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from ..conformance import boundary_provenance, load_actual
from ..conformance import run as run_conformance
from ..config import load as load_config
from ..errors import StoreError
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
        paths = [Path(a) for a in artifacts] or _configured(root)
        if not paths:
            click.echo("rqunit conformance: no actual-surface artifact configured "
                       "([stacks.<name>] actual_surface in rqunit.toml)", err=True)
            sys.exit(2)
        violations = run_conformance(store, root, paths)
        # What extraction actually reached. The manifest is allowed to exceed
        # what an extractor can see — that is how it carries target state — so
        # the unproven fraction has to be countable, or a green run reads as
        # "checked" when most of the boundary was never looked at (§5.6).
        provenance = boundary_provenance(store, [load_actual(p) for p in paths])
    except StoreError as e:
        click.echo(f"rqunit conformance: {e}", err=True)
        sys.exit(2)
    except Exception as e:
        click.echo(f"rqunit conformance: tool error: {e}", err=True)
        sys.exit(2)

    report = build_report("rqunit-conformance", violations, len(paths), root)
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


def _configured(root: Path) -> list[Path]:
    config = load_config(root)
    return [root / config.rust.actual_surface] if config.rust.actual_surface else []
