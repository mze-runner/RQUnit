"""Consumer configuration — `rqunit.toml` at the repo root.

Everything repo-specific the toolchain needs lives HERE, never in code. The
spec store itself is NOT configurable — its layout is fixed by spec §12.1
(`spec/` at the root), and projections/packets are part of that contract.

Stacks are open: any `[stacks.<name>]` table declares a stack, and core
carries no list of supported languages. Per stack, core interprets a CLOSED
set of keys — the `adapter` role declarations and `literal_scan` — and every
other key is the stack adapter's own configuration, carried opaquely in
`Stack.options` and never read by core. That line is what keeps the framework
stack-agnostic: a judgment about what `routers` or `trace_scan` mean would be
language knowledge, and language knowledge lives out of process.

A missing file means no stacks: store-only operations need zero
configuration, and stack participation is always an explicit declaration.
Unknown shapes among the keys core DOES interpret are errors (`BadConfig`) —
a typo silently ignored would read as configured. Passthrough keys are
validated against the adapter manifest's `config_keys`, not here.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .errors import BadConfig

_STACK_NAME = re.compile(r"^[a-z][a-z0-9_-]*$")

ROLES = ("extractor", "scanner", "emitter", "evidence", "stripper")


@dataclass(frozen=True)
class Role:
    """One adapter role: a command core execs (`cmd`), XOR an artifact an
    earlier pipeline step already produced (`artifact`). Exactly one — a role
    that could be both would leave which one ran ambiguous."""

    cmd: tuple[str, ...] = ()
    artifact: str = ""


@dataclass(frozen=True)
class Adapter:
    """The stack's declared adapter capability. An absent role means that
    capability is unavailable for this stack — reported as such by whatever
    needs it, never silently skipped."""

    manifest: str = ""
    extractor: Role | None = None
    scanner: Role | None = None
    emitter: Role | None = None
    evidence: Role | None = None
    # The off-ramp. Adoption asks a consumer to write trace annotations into
    # their own sources; a stack that declares no stripper can be adopted but
    # not un-adopted, and `rqunit trace --strip` says exactly that rather than
    # reporting a clean sweep it never performed.
    stripper: Role | None = None


@dataclass(frozen=True)
class Stack:
    name: str
    adapter: Adapter = Adapter()
    # Globs to tests/ DIRECTORIES for the hardcoded-bound advisory
    # (`rqunit generate scan-literals`). Core-read, but the sweep itself is
    # still Rust-specific (it globs *.rs), so only the rust stack's globs are
    # honored until the advisory moves behind an adapter role.
    literal_scan: tuple[str, ...] = ()
    # Everything else under [stacks.<name>] — adapter-owned, opaque to core.
    options: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class Config:
    stacks: tuple[Stack, ...] = ()

    def stack(self, name: str) -> Stack | None:
        for stack in self.stacks:
            if stack.name == name:
                return stack
        return None


# Keys core interprets per [stacks.<name>]; the rest is passthrough.
_CORE_KEYS = {"adapter", "literal_scan"}

# Keys core USED to interpret, and where each one went. Passthrough means core
# cannot judge an unknown key — that is deliberate, and adapters own their own
# vocabulary. But a RETIRED key is the one class core still recognises, because
# it used to own it: left where it was, it loads cleanly, lands in `options`
# beside live adapter keys, and silently configures nothing. A consumer reading
# their own file sees a setting; the tool sees a passthrough it will never
# read. Naming the successor turns that silent degradation into one line of
# instruction, and costs a constant.
# Each value is the COMPLETE instruction, not a fragment a template wraps.
# Retirement has two shapes — `actual_surface` moved somewhere, `trace_diff`
# simply died — and one phrasing cannot serve both: wrapping them in "Move it:
# …" tells a reader to relocate a key that has nowhere to go, and then to
# "delete the old key" as though a new one existed. A consumer meets this
# message exactly once, at upgrade, with no context but the sentence.
RETIRED_KEYS = {
    "actual_surface":
        'Declare it as [stacks.<name>.adapter] extractor = { artifact = "..." }, '
        "and delete the old key in the same edit.",
    "trace_diff":
        "Delete it — there is nowhere to move it to. L14 compares scanner "
        "observations between refs, so it needs no pathspecs (§6.6).",
}


def load(root: Path) -> Config:
    path = Path(root) / "rqunit.toml"
    if not path.is_file():
        return Config()
    try:
        data = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as e:
        raise BadConfig(str(path), f"not parseable TOML: {e}") from e
    unknown = set(data) - {"stacks"}
    if unknown:
        raise BadConfig(str(path), f"unknown top-level table(s): {', '.join(sorted(unknown))}")
    stacks_raw = data.get("stacks") or {}
    if not isinstance(stacks_raw, dict):
        raise BadConfig(str(path), "stacks must be a table of [stacks.<name>] tables")
    stacks = []
    for name in sorted(stacks_raw):
        if not _STACK_NAME.match(name):
            raise BadConfig(str(path), f"stack name '{name}' must match [a-z][a-z0-9_-]* — "
                                       "it names config tables and adapter directories")
        raw = stacks_raw[name]
        if not isinstance(raw, dict):
            raise BadConfig(str(path), f"[stacks.{name}] must be a table")
        stacks.append(_stack(path, name, raw))
    return Config(stacks=tuple(stacks))


def _stack(path: Path, name: str, raw: dict) -> Stack:
    literal = raw.get("literal_scan", [])
    if not isinstance(literal, list) or not all(isinstance(v, str) for v in literal):
        raise BadConfig(str(path), f"[stacks.{name}] literal_scan must be a list of glob strings")
    return Stack(
        name=name,
        adapter=_adapter(path, name, raw.get("adapter")),
        literal_scan=tuple(literal),
        options={k: v for k, v in raw.items() if k not in _CORE_KEYS},
    )


def _adapter(path: Path, name: str, raw: object) -> Adapter:
    if raw is None:
        return Adapter()
    if not isinstance(raw, dict):
        raise BadConfig(str(path), f"[stacks.{name}.adapter] must be a table")
    unknown = set(raw) - {"manifest", *ROLES}
    if unknown:
        raise BadConfig(str(path), f"unknown [stacks.{name}.adapter] key(s): "
                                   f"{', '.join(sorted(unknown))} "
                                   f"(supported: manifest, {', '.join(ROLES)})")
    manifest = raw.get("manifest", "")
    if not isinstance(manifest, str):
        raise BadConfig(str(path), f"[stacks.{name}.adapter] manifest must be a string path")
    roles = {role: _role(path, name, role, raw[role]) for role in ROLES if role in raw}
    return Adapter(manifest=manifest, **roles)


def _role(path: Path, stack: str, role: str, raw: object) -> Role:
    where = f"[stacks.{stack}.adapter] {role}"
    if not isinstance(raw, dict):
        raise BadConfig(str(path), f"{where} must be a table: "
                                   "{ cmd = [...] } or { artifact = \"path\" }")
    unknown = set(raw) - {"cmd", "artifact"}
    if unknown:
        raise BadConfig(str(path), f"unknown {where} key(s): {', '.join(sorted(unknown))} "
                                   "(supported: cmd, artifact)")
    if ("cmd" in raw) == ("artifact" in raw):
        raise BadConfig(str(path), f"{where} needs exactly one of `cmd` (core execs it) or "
                                   "`artifact` (core reads a file the pipeline produced)")
    if "cmd" in raw:
        cmd = raw["cmd"]
        if (not isinstance(cmd, list) or not cmd
                or not all(isinstance(v, str) and v for v in cmd)):
            raise BadConfig(str(path), f"{where} cmd must be a non-empty list of strings — "
                                       "argv, executed without a shell")
        return Role(cmd=tuple(cmd))
    artifact = raw["artifact"]
    if not isinstance(artifact, str) or not artifact:
        raise BadConfig(str(path), f"{where} artifact must be a non-empty repo-relative path")
    return Role(artifact=artifact)


def retired_key_uses(config: Config) -> list[tuple[str, str, str]]:
    """(stack, retired key, the instruction for it) for every dead setting a
    consumer still carries. Reported by `lint`; core reads none of them."""
    return [(stack.name, key, RETIRED_KEYS[key])
            for stack in config.stacks
            for key in sorted(stack.options)
            if key in RETIRED_KEYS]
