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
from jsonschema.exceptions import ValidationError, best_match

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
# First-party adapter self-declarations, shipped for the reason the schemas are:
# an adapter manifest is the vocabulary core validates a consumer's passthrough
# config against, and a consumer who installed the tool has no copy of this
# repository to point at.
ADAPTER_DIR = PACK_DIR / "adapters"


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


def describe_violation(error: ValidationError) -> str:
    """A schema failure in the ARTIFACT's terms, not the validator's.

    jsonschema reports a composite failure at the composite: for a schema whose
    root carries an `anyOf`, the message is the ENTIRE instance followed by "is
    not valid under any of the given schemas" — every key echoed back, none of
    them named as the problem, and no indication which of the branches was
    meant. That is the first error a consumer meets when they hand-write their
    first manifest, and Hard Rule 6 says a violation the reader has to research
    is a failure of the rule rather than of the reader.

    Two translations recover the intent:

    A disjunction of `required` branches is a real rule — "a service manifest
    must declare at least one surface family" — so it is reported as one, by
    name, rather than descended into. Descending would pick the first branch
    arbitrarily and say "'endpoints' is a required property", sending the reader
    to add the wrong thing.

    A `not` over a bare `required` is the mirror image — "this key is not
    allowed on this document" — and jsonschema reports it by echoing the whole
    instance back with the subschema appended. The key is in the subschema, so
    the rule can be stated instead.

    Everything else descends to the most specific sub-error jsonschema can
    rank, and is reported against its location in the document
    (`endpoints[0].id`), which is the part the reader has to go and edit."""
    while True:
        refused = _refused_keys(error)
        if refused:
            where = _location(error)
            subject = f"`{where}` declares" if where else "the document declares"
            return (f"{subject} {', '.join(refused)}, which this kind of artifact "
                    "does not carry")
        options = _required_disjunction(error)
        if options:
            where = _location(error)
            subject = f"`{where}` declares" if where else "the document declares"
            return (f"{subject} none of {', '.join(options)} — at least one is "
                    "required")
        if not error.context:
            break
        deeper = best_match(error.context)
        if deeper is None:
            break
        error = deeper
    where = _location(error)
    detail = error.message
    if len(detail) > _DETAIL_LIMIT:
        detail = detail[:_DETAIL_LIMIT] + " …"
    return f"`{where}`: {detail}" if where else detail


_DETAIL_LIMIT = 200


def _location(error: ValidationError) -> str:
    return error.json_path.removeprefix("$.").removeprefix("$")


def _refused_keys(error: ValidationError) -> list[str]:
    """The keys a `not: {required: [...]}` refuses.

    Bare branches only, for the reason the disjunction below gives: a `not` over
    anything richer than `required` denies a SHAPE, and naming its keys would
    describe the wrong rule."""
    if error.validator != "not":
        return []
    subschema = error.validator_value
    if not isinstance(subschema, dict) or set(subschema) != {"required"}:
        return []
    keys = subschema["required"]
    if not isinstance(keys, list) or not all(isinstance(k, str) for k in keys):
        return []
    return [f"`{k}`" for k in keys]


def _required_disjunction(error: ValidationError) -> list[str]:
    """The keys an `anyOf`/`oneOf` of bare `required` branches offers.

    Only bare branches qualify: `[{"required": ["a"]}, {"required": ["b"]}]` is
    a choice between keys, while a branch carrying anything else is a choice
    between SHAPES, and listing its required keys would describe neither."""
    if error.validator not in ("anyOf", "oneOf"):
        return []
    branches = error.validator_value or []
    if not branches or not all(isinstance(b, dict) and list(b) == ["required"]
                               for b in branches):
        return []
    return sorted({key for b in branches for key in b["required"]})
