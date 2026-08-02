"""Consumer configuration — `rqunit.toml` at the repo root (product Phase I).

Everything repo-specific the toolchain needs lives HERE, never in code: which
code trees participate in trace scanning, and where generated conformance
artifacts land. The spec store itself is NOT configurable — its layout is
fixed by spec §12.1 (`spec/` at the root), and projections/packets are part
of that contract.

A missing file (or missing keys) falls back to generic conventional defaults,
so store-only operations and fresh checkouts work with zero configuration.
Unknown tables or keys are errors (`BadConfig`): a typo silently ignored
would read as configured.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

from .errors import BadConfig


@dataclass(frozen=True)
class Router:
    """One mounted router: which function in which file, at what prefix, under
    which access tier. This is composition — a fact about THIS repository's
    layout, not about Rust or about axum — so it is configuration. It lived as
    a constant in adapter source, which put a consumer's file paths and service
    names inside the product."""

    file: str
    function: str
    prefix: str = ""
    access: str = ""


@dataclass(frozen=True)
class Messages:
    """Where async subjects are declared and who publishes them."""

    # Files or directories declaring subject constants.
    subject_sources: tuple[str, ...] = ()
    # Files or directories whose code references those constants — what the
    # service actually publishes, as opposed to what it could name.
    publisher_sources: tuple[str, ...] = ()


@dataclass(frozen=True)
class Audit:
    """Where audit codes are declared, and which sources record them.

    Same shape as `Messages` because it is the same question: naming a code is
    not emitting one, so declaration sources and emission sources are separate
    inputs."""

    code_sources: tuple[str, ...] = ()
    emitter_sources: tuple[str, ...] = ()


@dataclass(frozen=True)
class RustStack:
    # Globs (repo-root-relative) to the Cargo.toml of every crate whose
    # tests/ directory participates in verifies-tracing (`rqunit trace`).
    trace_scan: tuple[str, ...] = ("**/Cargo.toml",)
    # Git pathspecs for the L14 new-test diff gate.
    trace_diff: tuple[str, ...] = ("*/tests/*.rs",)
    # Globs to tests/ DIRECTORIES for the hardcoded-bound advisory
    # (`rqunit generate scan-literals`).
    literal_scan: tuple[str, ...] = ("**/tests",)
    # Path of the crate receiving generated constants and statechart suites.
    # Its basename doubles as the package name prefixing trace-map check ids.
    conformance_crate: str = "spec-conformance-tests"
    # Where this stack's extractor writes actual-surface.json — the artifact
    # `rqunit conformance` reconciles against the manifests. Empty disables.
    actual_surface: str = "spec-conformance-tests/actual-surface.json"
    # Manifest service slug this stack's extractor reports on. Empty means the
    # extractor cannot key its output and conformance is not attempted.
    service: str = ""
    # HTTP composition table (see Router).
    routers: tuple[Router, ...] = ()
    # Async surface discovery.
    messages: Messages = Messages()
    # Audit emission discovery.
    audit: Audit = Audit()


@dataclass(frozen=True)
class Config:
    rust: RustStack = RustStack()


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
    stacks = data.get("stacks") or {}
    unknown = set(stacks) - {"rust"}
    if unknown:
        raise BadConfig(str(path), f"unknown stack(s): {', '.join(sorted(unknown))} "
                                   "(supported: rust)")
    rust_raw = stacks.get("rust") or {}
    known = {f.name for f in fields(RustStack)}
    unknown = set(rust_raw) - known
    if unknown:
        raise BadConfig(str(path), f"unknown [stacks.rust] key(s): {', '.join(sorted(unknown))} "
                                   f"(supported: {', '.join(sorted(known))})")
    kwargs = {}
    for name in known & set(rust_raw):
        value = rust_raw[name]
        if name == "routers":
            kwargs[name] = _routers(path, value)
        elif name == "messages":
            kwargs[name] = _messages(path, value)
        elif name == "audit":
            kwargs[name] = _audit(path, value)
        elif name in ("conformance_crate", "service"):
            if not isinstance(value, str) or (name == "conformance_crate" and not value):
                raise BadConfig(str(path), f"{name} must be a non-empty string")
            kwargs[name] = value
        elif name == "actual_surface":
            if not isinstance(value, str):
                raise BadConfig(str(path), "actual_surface must be a string path ('' disables)")
            kwargs[name] = value
        else:
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise BadConfig(str(path), f"{name} must be a list of glob strings")
            kwargs[name] = tuple(value)
    return Config(rust=RustStack(**kwargs))


def _routers(path: Path, value: object) -> tuple[Router, ...]:
    if not isinstance(value, list):
        raise BadConfig(str(path), "routers must be a list of [[stacks.rust.routers]] tables")
    out = []
    for entry in value:
        if not isinstance(entry, dict):
            raise BadConfig(str(path), "each router must be a table")
        unknown = set(entry) - {"file", "function", "prefix", "access"}
        if unknown:
            raise BadConfig(str(path), f"unknown router key(s): {', '.join(sorted(unknown))} "
                                       "(supported: file, function, prefix, access)")
        missing = {"file", "function"} - set(entry)
        if missing:
            raise BadConfig(str(path), f"router is missing {', '.join(sorted(missing))} — an "
                                       "extractor cannot find a router it cannot name")
        out.append(Router(file=entry["file"], function=entry["function"],
                          prefix=entry.get("prefix", ""), access=entry.get("access", "")))
    return tuple(out)


def _messages(path: Path, value: object) -> Messages:
    if not isinstance(value, dict):
        raise BadConfig(str(path), "messages must be a [stacks.rust.messages] table")
    unknown = set(value) - {"subject_sources", "publisher_sources"}
    if unknown:
        raise BadConfig(str(path), f"unknown messages key(s): {', '.join(sorted(unknown))} "
                                   "(supported: subject_sources, publisher_sources)")
    for key in ("subject_sources", "publisher_sources"):
        entries = value.get(key, [])
        if not isinstance(entries, list) or not all(isinstance(v, str) for v in entries):
            raise BadConfig(str(path), f"{key} must be a list of path strings")
    return Messages(
        subject_sources=tuple(value.get("subject_sources", [])),
        publisher_sources=tuple(value.get("publisher_sources", [])),
    )


def _audit(path: Path, value: object) -> Audit:
    if not isinstance(value, dict):
        raise BadConfig(str(path), "audit must be a [stacks.rust.audit] table")
    unknown = set(value) - {"code_sources", "emitter_sources"}
    if unknown:
        raise BadConfig(str(path), f"unknown audit key(s): {', '.join(sorted(unknown))} "
                                   "(supported: code_sources, emitter_sources)")
    for key in ("code_sources", "emitter_sources"):
        entries = value.get(key, [])
        if not isinstance(entries, list) or not all(isinstance(v, str) for v in entries):
            raise BadConfig(str(path), f"{key} must be a list of path strings")
    return Audit(code_sources=tuple(value.get("code_sources", [])),
                 emitter_sources=tuple(value.get("emitter_sources", [])))
