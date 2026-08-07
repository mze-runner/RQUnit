"""`spec-assemble` — materialize task packets (§9.1); `--arm` engages the
H1/H2 hooks by pointing spec/packets/.active at the new packet."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from ..assemble import MODES, packet_path, render_packet
from ..schemas import repo_root
from ..store import Store


@click.group()
def main() -> None:
    """Context assembly."""


@main.command()
@click.argument("task")
@click.option("--ru", "ru_ids", multiple=True, required=True, help="Task RU ids (repeatable).")
@click.option("--store", "store_path", type=click.Path(path_type=Path), default=None)
@click.option("--arm", is_flag=True, help="Set spec/packets/.active to this packet (H1/H2 engage).")
@click.option("--mode", type=click.Choice(MODES), default="implementation",
              help="check-authoring assembles a packet for writing the checks BEFORE "
                   "the implementation exists; the mode is recorded in the packet.")
def build(task, ru_ids, store_path, arm, mode) -> None:
    try:
        root = store_path or repo_root()
        store = Store.load(root)
        content = render_packet(store, root, task, list(ru_ids), mode=mode)
    except ValueError as e:
        click.echo(f"spec-assemble: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"spec-assemble: tool error: {e}", err=True)
        sys.exit(2)
    target = packet_path(root, task)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    click.echo(f"wrote {target.relative_to(root)} ({mode})")
    if arm:
        (target.parent / ".active").write_text(target.name + "\n")
        click.echo(f"armed H1/H2 for {target.name}")


@main.command()
@click.option("--store", "store_path", type=click.Path(path_type=Path), default=None)
def disarm(store_path) -> None:
    root = store_path or repo_root()
    marker = Path(root) / "spec" / "packets" / ".active"
    if marker.exists():
        marker.unlink()
        click.echo("disarmed — H1/H2 inert")
    else:
        click.echo("already disarmed")
