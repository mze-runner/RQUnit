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
        if name == "conformance_crate":
            if not isinstance(value, str) or not value:
                raise BadConfig(str(path), "conformance_crate must be a non-empty string")
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
