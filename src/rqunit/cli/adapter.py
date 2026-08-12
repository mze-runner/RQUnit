"""`rqunit adapter verify` — the executable definition of a correct adapter.

A team adds a language by making this pass, without reading the framework's
source: for every role the manifest declares, the kit's fixed input produces
byte-deterministic, schema-valid output matching the committed expectation,
under the stdio exit contract. The framework owns the verifier, the schemas,
and the emitter's input fixture (it ships with the tool); the adapter owns
its kit trees and expected outputs, bound by the same no-consumer-leakage
rule as every fixture.

Kit layout is one convention, not a knob: `<kit>/<role>/tree/` is the role's
input (probes only) and `<kit>/<role>/expected.json` its expectation.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import click

from ..config import Stack, load as load_config
from ..errors import StoreError
from ..invoke import (TIMEOUT_SECONDS, load_adapter_manifest, manifest_path,
                      resolve_command, validate_payload)
from ..schemas import PACK_DIR

ROLE_SCHEMAS = {
    "extractor": "actual-surface.schema.json",
    "scanner": "scanned-checks.schema.json",
    "emitter": "emitted-files.schema.json",
    "evidence": "check-evidence.schema.json",
    "stripper": "stripped-files.schema.json",
}

# Roles whose kit input includes a request on stdin. The emitter's ships with
# the tool because it is a pure function of a plan the framework owns; the
# stripper's cannot, because it names files in the ADAPTER's own kit tree —
# so the adapter supplies it and core validates it against the pinned request
# schema, which keeps the shape the framework's while the content stays the
# adapter's.
KIT_REQUESTS = {"stripper": "strip-request.schema.json"}

EMIT_REQUEST = PACK_DIR / "kit" / "emit-request.json"


def _run(argv: list[str], cwd: Path, stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                          input=stdin, timeout=TIMEOUT_SECONDS)


def _verify_role(role: str, argv: list[str], base: Path, kit: Path) -> list[str]:
    """Every problem one role's kit run surfaces. `base` is the manifest's
    directory — kit commands resolve against it (the same rule the runtime
    uses), because the adapter knows where its own build puts binaries."""
    resolved = [resolve_command(base, argv[0]), *argv[1:]]

    if role == "emitter":
        stdin = EMIT_REQUEST.read_text()
        # An emitter is a pure function of its request: it gets an empty tree
        # to prove it, so one that reads past its plan fails the kit instead
        # of being rewarded by it.
        with tempfile.TemporaryDirectory(prefix="rqunit-kit-emit-") as barren:
            return _judge(role, resolved, base, Path(barren), stdin,
                          kit / role / "expected.json")
    tree = kit / role / "tree"
    if not tree.is_dir():
        return [f"{role}: kit has no input tree at {tree} — the kit layout is "
                f"<kit>/{role}/tree/ with the expectation at <kit>/{role}/expected.json"]

    stdin = ""
    if role in KIT_REQUESTS:
        request = kit / role / "request.json"
        if not request.is_file():
            return [f"{role}: kit has no request at {request} — this role is driven by a "
                    "request on stdin, and the request names files in the kit tree, so "
                    "the adapter supplies it"]
        stdin = request.read_text()
        try:
            validate_payload(json.loads(stdin), KIT_REQUESTS[role], str(request))
        except json.JSONDecodeError as e:
            return [f"{role}: kit request is unparseable JSON: {e}"]
        except StoreError as e:
            return [f"{role}: kit request is not a valid request — {e}"]

    return _judge(role, resolved, base, tree, stdin, kit / role / "expected.json")


def _judge(role: str, resolved: list[str], base: Path, root: Path, stdin: str,
           expected_path: Path) -> list[str]:
    full = [*resolved, "--root", str(root)]
    try:
        first = _run(full, base, stdin)
    except FileNotFoundError:
        return [f"{role}: command '{resolved[0]}' does not exist — build the adapter "
                "first (its own toolchain, never this one), or fix kit.commands"]
    except subprocess.TimeoutExpired:
        return [f"{role}: produced nothing for {TIMEOUT_SECONDS}s on its kit input — "
                "a role that hangs on a fixed fixture is non-compliant"]
    if first.returncode != 0:
        return [f"{role}: exited {first.returncode} on its kit input — stderr:\n"
                f"{first.stderr.strip() or '(no stderr)'}"]
    problems = []
    second = _run(full, base, stdin)
    if first.stdout != second.stdout:
        problems.append(f"{role}: two runs over the same input differ — output must be "
                        "a byte-deterministic function of the input (§5.6)")
    try:
        data = validate_payload(json.loads(first.stdout), ROLE_SCHEMAS[role],
                                f"{role} kit run")
    except json.JSONDecodeError as e:
        return problems + [f"{role}: emitted unparseable JSON on stdout: {e}"]
    except StoreError as e:
        return problems + [f"{role}: {e}"]

    if not expected_path.is_file():
        problems.append(f"{role}: kit has no expected output at {expected_path} — "
                        "commit the expectation the kit run must match")
    elif json.loads(expected_path.read_text()) != data:
        problems.append(f"{role}: output diverges from {expected_path} — either the "
                        "adapter changed behaviour (fix it) or the behaviour change is "
                        "intended (regenerate and commit the expectation)")

    if role == "scanner":
        with tempfile.TemporaryDirectory(prefix="rqunit-kit-empty-") as empty:
            problems.extend(_empty_tree_probe(resolved, base, Path(empty)))
    if role in ("emitter", *KIT_REQUESTS):
        starved = _run(full, base, stdin="")
        if starved.returncode == 0:
            problems.append(f"{role}: exited 0 with no request on stdin — silence in "
                            "must not become an artifact out")
    return problems


def _empty_tree_probe(resolved: list[str], base: Path, empty: Path) -> list[str]:
    """Judged as parsed structure, never as serialized text — a compliant
    scanner may format its JSON however it likes."""
    probe = _run([*resolved, "--root", str(empty)], base)
    message = ("scanner: a tree that declares nothing must yield exit 0 and zero "
               "checks — 'nothing participates' is an observation, not an error")
    if probe.returncode != 0:
        return [message]
    try:
        data = validate_payload(json.loads(probe.stdout), ROLE_SCHEMAS["scanner"],
                                "scanner empty-tree probe")
    except (json.JSONDecodeError, StoreError):
        return [message]
    return [] if data["checks"] == [] else [message]


@click.group()
def main() -> None:
    """Adapter compliance."""


@main.command()
@click.option("--stack", "stack_name", required=True, help="Stack whose adapter to verify.")
@click.option("--root", "root_path", type=click.Path(path_type=Path), default=None,
              help="Repository root holding the adapter (default: current directory).")
def verify(stack_name: str, root_path: Path | None) -> None:
    """Run the declared roles against the adapter's compliance kit."""
    root = Path(root_path or Path.cwd()).resolve()
    try:
        config = load_config(root)
        stack = config.stack(stack_name) or Stack(name=stack_name)
        manifest = load_adapter_manifest(root, stack)
        if manifest is None:
            click.echo(f"rqunit adapter: no manifest for stack '{stack_name}' "
                       f"(looked at {manifest_path(root, stack)}) — the manifest "
                       "declares the roles and kit this command verifies", err=True)
            sys.exit(2)
        kit_decl = manifest.get("kit")
        if not kit_decl:
            click.echo(f"rqunit adapter: the '{stack_name}' manifest declares no kit — "
                       "add kit: { path, commands } so correctness is executable, "
                       "not asserted in prose", err=True)
            sys.exit(2)
        base = manifest_path(root, stack).parent
        kit = (base / kit_decl["path"]).resolve()
        problems = []
        ran = []
        for role in manifest["roles"]:
            argv = (kit_decl.get("commands") or {}).get(role)
            if not argv:
                problems.append(f"{role}: declared in roles but kit.commands has no "
                                "entry for it — a role the kit cannot run is unverified")
                continue
            ran.append(role)
            problems.extend(_verify_role(role, list(argv), base, kit))
    except StoreError as e:
        click.echo(f"rqunit adapter: {e}", err=True)
        sys.exit(2)

    for problem in problems:
        click.echo(f"FAIL {problem}", err=True)
    click.echo(f"adapter verify · stack {stack_name} · "
               f"ran: {', '.join(ran) or 'nothing'} · {len(problems)} problem(s)")
    sys.exit(1 if problems else 0)
