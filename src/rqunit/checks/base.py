"""Check registry (TASK-040…048)."""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable

from ..store import Store
from ..violations import Violation

REGISTRY: dict[str, Callable[[Store], list[Violation]]] = {}


def check(code: str):
    def register(fn):
        REGISTRY[code] = fn
        fn.code = code
        return fn
    return register


def discover() -> dict[str, Callable]:
    pkg = importlib.import_module("rqunit.checks")
    for mod in pkgutil.iter_modules(pkg.__path__):
        if mod.name.startswith("c") and mod.name[1:].isdigit():
            importlib.import_module(f"rqunit.checks.{mod.name}")
    return REGISTRY


def run_checks(store: Store, only: str | None = None) -> list[Violation]:
    discover()
    codes = [only] if only else sorted(REGISTRY, key=lambda c: int(c[1:]))
    out: list[Violation] = []
    for code in codes:
        out.extend(REGISTRY[code](store))
    return out
