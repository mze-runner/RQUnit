"""Schemas and store discovery.

Two lookups that used to be one, separated by the extraction:

* **Schemas ship with the tool.** They live in ``pack/schemas/`` inside this
  package, so a store is always validated against the schemas of the version
  enforcing it. That is what makes a pinned pack version meaningful, and it is
  why the tool works as an installed dependency — nothing is read relative to
  the source tree.
* **Stores are discovered from the caller.** ``store_root`` walks up from the
  INVOCATION directory, never from this module's location: an installed CLI
  lives in a virtualenv that has no relationship to the repository being
  governed.
"""

from __future__ import annotations

import functools
import importlib.metadata
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

SCHEMA_FILES = {
    "ru": "ru.schema.yaml",
    "manifest": "manifest.schema.yaml",
    "model": "model.statechart.schema.yaml",
    "feat": "feat.schema.yaml",
    "gap": "gap.schema.yaml",
}

PACK_DIR = Path(__file__).parent / "pack"
SCHEMA_DIR = PACK_DIR / "schemas"
SEED_DIR = PACK_DIR / "seeds"


def store_root(start: Path | None = None) -> Path:
    """The consumer store root: the nearest ancestor of ``start`` (default:
    the current directory) containing ``spec/``."""
    here = (start or Path.cwd()).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "spec").is_dir():
            return candidate
    raise FileNotFoundError(
        f"no spec/ store at or above {here} — run `rqunit init` to create one, "
        "or pass --store")


# Retained name for call sites that predate the extraction; a store root is
# what every one of them actually meant.
repo_root = store_root


# The SPECIFICATION version this build implements — the vocabulary a store is
# authored against. Deliberately NOT the package version: a tool fix (a crash,
# a message) changes no vocabulary, and forcing a spec revision for one would
# make consumers re-read a document that did not change. The adapter contract
# already works this way (`contract_version`), for the same reason.
#
# A meta-test ties this to the status line in docs/ru-framework-spec.md; the two
# move together or the build says so.
SPEC_VERSION = "0.16.0"


def installed_version() -> str:
    """The version of the TOOL doing the enforcing (the installed package)."""
    try:
        return importlib.metadata.version("rqunit")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def store_pack_version(root: Path) -> str:
    """The SPEC version a store was authored against, from
    ``spec/framework/pack.yaml`` (written by ``rqunit init``).

    Falls back to this build's ``SPEC_VERSION``: a store predating the pin is
    not broken, it is merely unpinned, and reporting the enforcing version is a
    better answer than reporting nothing."""
    path = Path(root) / "spec" / "framework" / "pack.yaml"
    if path.is_file():
        pinned = (yaml.safe_load(path.read_text()) or {}).get("pack")
        if isinstance(pinned, str) and pinned:
            return pinned
    return SPEC_VERSION


@functools.lru_cache(maxsize=None)
def load_schema(kind: str) -> dict:
    schema = yaml.safe_load((SCHEMA_DIR / SCHEMA_FILES[kind]).read_text())
    Draft202012Validator.check_schema(schema)
    return schema


def validator(kind: str) -> Draft202012Validator:
    return Draft202012Validator(load_schema(kind))
