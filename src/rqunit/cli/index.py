"""`spec-index` — regenerate the machine index and surface sheets (§11).
Thin wrapper over the same renderers `spec-generate` guards, so there is one
source of truth for projection content."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from ..generate import render_ru_index, render_sheet_file
from ..schemas import repo_root
from ..store import Store


@click.command()
@click.option("--store", "store_path", type=click.Path(path_type=Path), default=None)
def main(store_path: Path | None) -> None:
    try:
        root = store_path or repo_root()
        store = Store.load(root)
    except Exception as e:
        click.echo(f"spec-index: tool error: {e}", err=True)
        sys.exit(2)
    projections = Path(root) / "spec" / "projections"
    targets = {projections / "ru-index.json": render_ru_index(store)}
    for service in store.manifests():
        targets[projections / "surface-sheets" / f"{service}.md"] = \
            render_sheet_file(store, service)
    for path, content in targets.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or path.read_text() != content:
            path.write_text(content)
            click.echo(f"wrote {path.relative_to(root)}")
