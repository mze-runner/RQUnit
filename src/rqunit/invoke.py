"""Adapter invocation — the one place core touches an adapter.

Two transports per declared role, both consumer-declared in rqunit.toml
(`[stacks.<name>.adapter]`): `cmd`, where core execs the declared argv with
`--root <abs path>` appended, no shell, and reads JSON from stdout; and
`artifact`, where core reads a file an earlier pipeline step produced. Core
treats the command as a black box behind the role's pinned schema — it never
invokes a language toolchain, never builds anything, and judges nothing an
adapter reports.

Exit contract for cmd mode: 0 ok / 1 probe failure / 2 tool error. Both
failure classes surface as configuration errors with the adapter's stderr
attached, because the adapter's message IS its interface.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, ValidationError

from .config import ROLES, Stack
from .errors import BadConfig, RoleUnavailable

INTERFACES = Path(__file__).parent / "interfaces"

# Contract versions this build reads. A single integer per artifact:
# negotiation is membership in this set, never semver arithmetic.
SUPPORTED_CONTRACTS = (1,)

MANIFEST_SCHEMA = "adapter-manifest.schema.json"

# A probe that has produced nothing for this long is not observing — it is
# stuck, usually reading a terminal nobody is watching. The gate fails loudly
# instead of hanging a commit hook.
TIMEOUT_SECONDS = 600


def run_role(root: Path, stack: Stack, role_name: str, schema: str,
             target_root: Path | None = None,
             stdin_payload: str | None = None) -> dict:
    """One adapter role's output, parsed and validated against its pinned
    schema — the single door for both transports, so every caller gets the
    same checks. `schema` is the contract file under interfaces/.

    `target_root` points the role at a different tree to observe (the L14
    base scan runs the scanner over a detached checkout): the command still
    resolves and runs from `root`, where the built adapter lives, but its
    `--root` — and an artifact-mode read — is the target tree."""
    role = getattr(stack.adapter, role_name)
    if role is None:
        raise RoleUnavailable(
            None,
            f"stack '{stack.name}' declares no {role_name} — declare "
            f"[stacks.{stack.name}.adapter] {role_name} = {{ cmd = [...] }} or "
            "{ artifact = \"path\" } in rqunit.toml")
    root = Path(root).resolve()      # the documented promise: --root is absolute
    target = Path(target_root).resolve() if target_root is not None else root
    if role.artifact:
        return _from_artifact(target, role.artifact, role_name, schema)
    return _from_cmd(root, target, stack, role_name, role.cmd, schema, stdin_payload)


def _from_artifact(root: Path, artifact: str, role_name: str, schema: str) -> dict:
    path = root / artifact
    if not path.is_file():
        raise BadConfig(str(path),
                        f"no {role_name} artifact — produce it in your own pipeline "
                        "(that is what artifact mode is for), or declare cmd = [...] "
                        "so core can run the adapter itself")
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise BadConfig(str(path), f"not parseable JSON: {e}") from e
    return validate_payload(data, schema, str(path))


def _from_cmd(root: Path, target: Path, stack: Stack, role_name: str,
              cmd: tuple[str, ...], schema: str,
              stdin_payload: str | None = None) -> dict:
    where = f"[stacks.{stack.name}.adapter] {role_name}"
    argv = [resolve_command(root, cmd[0]), *cmd[1:], "--root", str(target)]
    try:
        # The emitter reads its request on stdin; probes get stdin at EOF so
        # one that prompts fails fast instead of hanging the gate.
        proc = subprocess.run(argv, cwd=root, capture_output=True, text=True,
                              input=stdin_payload if stdin_payload is not None else "",
                              timeout=TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        raise BadConfig(where,
                        f"{role_name} produced nothing for {TIMEOUT_SECONDS}s and was "
                        "stopped. If the probe is legitimately this slow, run it in "
                        "your own pipeline and declare artifact = \"path\" instead") from None
    except FileNotFoundError:
        raise BadConfig(where,
                        f"'{cmd[0]}' does not exist — build the adapter in its own "
                        "toolchain first (core never builds it), or declare "
                        "artifact = \"path\" and produce the file in an earlier "
                        "pipeline step") from None
    except OSError as e:
        raise BadConfig(where, f"could not exec '{cmd[0]}': {e}") from e
    stderr = proc.stderr.strip() or "(no stderr)"
    if proc.returncode == 1:
        raise BadConfig(where, f"{role_name} reported a probe failure:\n{stderr}")
    if proc.returncode != 0:
        raise BadConfig(where, f"{role_name} tool error (exit {proc.returncode}):\n{stderr}")
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise BadConfig(where, f"emitted unparseable JSON on stdout: {e} — a probe's "
                               "stdout is its artifact; logs belong on stderr") from e
    return validate_payload(data, schema, where)


def resolve_command(root: Path, cmd0: str) -> str:
    """A relative command resolves against `root` (where the declared adapter
    binary lives), falling back to PATH lookup — one resolution rule for both
    the runtime and the compliance kit, or the kit certifies something
    different from what core runs."""
    path = Path(cmd0)
    if not path.is_absolute() and (root / path).exists():
        return str(root / path)
    return cmd0


def validate_payload(data: object, schema_file: str, where: str) -> dict:
    if not isinstance(data, dict):
        raise BadConfig(where, "adapter output must be a JSON object")
    version = data.get("contract_version")
    if version not in SUPPORTED_CONTRACTS:
        supported = ", ".join(str(v) for v in SUPPORTED_CONTRACTS)
        raise BadConfig(where,
                        f"contract_version {version!r} is not supported — this rqunit "
                        f"reads contract_version {supported}. Upgrade the tool, or the "
                        "adapter, until the two agree; neither guesses across a "
                        "version it does not know.")
    schema = json.loads((INTERFACES / schema_file).read_text())
    contract = schema_file.removesuffix(".schema.json")
    try:
        Draft202012Validator(schema).validate(data)
    except ValidationError as e:
        raise BadConfig(where, f"does not match the {contract} contract: {e.message}") from e
    return data


# ------------------------------------------------------------ adapter manifest

def manifest_path(root: Path, stack: Stack) -> Path:
    declared = stack.adapter.manifest
    if declared:
        return Path(root) / declared
    return Path(root) / "adapters" / stack.name / "adapter.yaml"


def load_adapter_manifest(root: Path, stack: Stack) -> dict | None:
    """The adapter's self-declaration, or None when the stack has no manifest
    (only a DECLARED manifest path that resolves to nothing is an error)."""
    path = manifest_path(root, stack)
    if not path.is_file():
        if stack.adapter.manifest:
            raise BadConfig(str(path),
                            f"[stacks.{stack.name}.adapter] manifest points at a file "
                            "that does not exist — fix the path, or delete the key to "
                            "run without manifest validation")
        return None
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        raise BadConfig(str(path), f"not parseable YAML: {e}") from e
    data = validate_payload(data, MANIFEST_SCHEMA, str(path))
    if data["stack"] != stack.name:
        raise BadConfig(str(path),
                        f"manifest declares stack '{data['stack']}' but is wired to "
                        f"[stacks.{stack.name}] — a manifest on the wrong stack would "
                        "validate the wrong vocabulary")
    return data


def stack_declaration_problems(root: Path, stack: Stack) -> list[str]:
    """Consumer-config health only a manifest can judge: passthrough keys the
    adapter does not read (typo detection), and declared roles the adapter
    does not implement. Empty when the stack ships no manifest — the caller
    decides whether unvalidated config is worth a finding."""
    manifest = load_adapter_manifest(root, stack)
    if manifest is None:
        return []
    problems = []
    known = set(manifest.get("config_keys") or [])
    unknown = sorted(set(stack.options) - known)
    if unknown:
        problems.append(
            f"[stacks.{stack.name}] key(s) the adapter does not read: "
            f"{', '.join(unknown)} — fix the typo, or add the key to the adapter "
            f"manifest's config_keys ({manifest_path(root, stack)})")
    implemented = set(manifest.get("roles") or [])
    for role_name in ROLES:
        if getattr(stack.adapter, role_name) is not None and role_name not in implemented:
            problems.append(
                f"[stacks.{stack.name}.adapter] declares {role_name}, but the adapter "
                f"manifest does not list that role — the exec would fail; wire the "
                "role the adapter actually ships")
    return problems
