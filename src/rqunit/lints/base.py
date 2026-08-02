"""Lint registry (TASK-012…029). One module per lint under rqunit.lints,
self-registering via @lint("Lnn"); the CLI auto-discovers by importing the
package's modules. L14 is deliberately absent — its `verifies()` resolver is
TASK-080 (Phase 7); registering a no-op would report a green it cannot see.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable
from pathlib import Path

import yaml

from ..parser.ears import EarsParseError, Statement, parse
from ..parser.tokens import extract
from ..store import Ru, Store
from ..violations import Violation

REGISTRY: dict[str, Callable[[Store], list[Violation]]] = {}


def lint(code: str):
    def register(fn):
        REGISTRY[code] = fn
        fn.code = code
        return fn
    return register


def discover() -> dict[str, Callable]:
    pkg = importlib.import_module("rqunit.lints")
    for mod in pkgutil.iter_modules(pkg.__path__):
        if mod.name.startswith("l") and mod.name[1:].isdigit():
            importlib.import_module(f"rqunit.lints.{mod.name}")
    return REGISTRY


def run_lints(store: Store, only: str | None = None) -> list[Violation]:
    discover()
    codes = [only] if only else sorted(REGISTRY, key=lambda c: int(c[1:]))
    out: list[Violation] = []
    for code in codes:
        out.extend(REGISTRY[code](store))
    return out


# ------------------------------------------------------------ shared helpers

def rel(store: Store, path) -> str:
    try:
        return str(Path(path).relative_to(store.root))
    except ValueError:
        return str(path)


def safe_parse(ru: Ru) -> Statement | None:
    """Parse an RU statement, or None if unparseable — reporting that is L1's
    job; downstream lints skip rather than double-report."""
    try:
        return parse(ru.raw["statement"], ru.raw.get("syntax", "ears"))
    except EarsParseError:
        return None


def load_wordlist(name: str) -> dict:
    return yaml.safe_load((Path(__file__).parent / name).read_text())


def manifest_value_leaves(values: dict, prefix: str = "") -> dict[str, object]:
    """Flatten a manifest `values` tree to {dotted.key: scalar}."""
    out: dict[str, object] = {}
    for key, node in (values or {}).items():
        dotted = f"{prefix}.{key}" if prefix else key
        if isinstance(node, dict):
            out.update(manifest_value_leaves(node, dotted))
        else:
            out[dotted] = node
    return out


def reachable_manifests(store: Store, ru: Ru) -> list:
    """The manifests an unqualified reference can see from this RU (§5.3):
    its scope service (plan D-P1.1 heuristic), then shared."""
    out = []
    scope = store.scope_service(ru)
    manifests = store.manifests()
    if scope and scope in manifests:
        out.append(manifests[scope])
    if "shared" in manifests:
        out.append(manifests["shared"])
    return out


def prose(text: str) -> str:
    """The statement with every valid reference-token span blanked.

    A token is a manifest identifier the author REFERENCED, not words they
    chose, so prose-scanning lints must not read inside one. Malformed tokens
    stay visible: they are L15's class, and hiding them would hide the defect.
    """
    tokens, _ = extract(text)
    for token in sorted(tokens, key=lambda t: -t.start):
        text = text[:token.start] + " " * len(token.raw) + text[token.start + len(token.raw):]
    return text
