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
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

SCHEMA_FILES = {
    "ru": "ru.schema.yaml",
    "manifest": "manifest.schema.yaml",
    "model": "model.statechart.schema.yaml",
    "feat": "feat.schema.yaml",
    "gap": "gap.schema.yaml",
    "contract": "contract.schema.yaml",
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


@functools.lru_cache(maxsize=None)
def load_schema(kind: str) -> dict:
    schema = yaml.safe_load((SCHEMA_DIR / SCHEMA_FILES[kind]).read_text())
    Draft202012Validator.check_schema(schema)
    return schema


def validator(kind: str) -> Draft202012Validator:
    return Draft202012Validator(load_schema(kind))
