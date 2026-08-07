"""Read-only spec-store loader (TASK-003, spec §12.2/§12.3).

Walks ``spec/``, parses artifacts, validates shapes against the framework
schemas, enforces filename↔id conventions (feeds L9), computes content hashes
for manifests and models (§5.6/§6.3), and resolves reference tokens per §5.3
(v0.10 qualifier rules). Loading is deterministic: directory listings are
sorted, artifacts are exposed in id order.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from jsonschema import ValidationError

from .errors import (
    FilenameIdMismatch,
    MalformedRef,
    MalformedYaml,
    SchemaInvalid,
    UnknownArtifact,
    UnresolvedRef,
)
from .parser.tokens import TokenError, parse_one
from .schemas import validator

_IGNORED = {"README.md", ".gitkeep", ".DS_Store"}

_RU_FILE = re.compile(r"^RU-(draft-[0-9A-HJKMNP-TV-Z]{26}|[0-9]{4})\.yaml$")
_FEAT_FILE = re.compile(r"^FEAT-[a-z0-9-]+\.yaml$")
_GAP_FILE = re.compile(r"^GAP-[0-9A-HJKMNP-TV-Z]{26}\.yaml$")
_MANIFEST_FILE = re.compile(r"^[a-z][a-z0-9-]*\.manifest\.yaml$")
_MODEL_FILE = re.compile(r"^MDL-[a-z][a-z0-9-]*\.statechart\.json$")
_INT_FILE = re.compile(r"^INT-[0-9]{4}\.[a-z0-9]+$")
_ADR_FILE = re.compile(r"^ADR-[A-Za-z0-9-]+\.md$")

# Reference token grammar (formats §2): parser.tokens owns it outright. This
# module used to carry a second regex "kept in lockstep" by hand; v0.13 retires
# it, because two implementations of one grammar are a drift class rather than a
# safeguard — the same reasoning that keeps ONE canonicalizer.


@dataclass(frozen=True)
class Artifact:
    path: Path
    raw: dict


@dataclass(frozen=True)
class Ru(Artifact):
    id: str = ""
    status: str = ""
    tier: str = "standard"


@dataclass(frozen=True)
class Feat(Artifact):
    id: str = ""


@dataclass(frozen=True)
class Gap(Artifact):
    id: str = ""
    severity: str = ""


@dataclass(frozen=True)
class Manifest(Artifact):
    service: str = ""
    content_hash: str = ""


@dataclass(frozen=True)
class Model(Artifact):
    id: str = ""  # bare id; the MDL- prefix lives in filename/refs
    content_hash: str = ""



@dataclass(frozen=True)
class Resolved:
    """A resolved reference: the owning manifest, the entry (or scalar), and
    the token parts that got it there."""

    kind: str
    key: str
    service: str
    value: object


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _load_yaml(path: Path) -> dict:
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise MalformedYaml(str(path), str(e)) from e
    if not isinstance(data, dict):
        raise MalformedYaml(str(path), "artifact is not a mapping")
    return data


def _load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise MalformedYaml(str(path), str(e)) from e
    if not isinstance(data, dict):
        raise MalformedYaml(str(path), "artifact is not a mapping")
    return data


def _validate(kind: str, data: dict, path: Path) -> None:
    # Schemas are framework-level: they always come from the repo's
    # spec/framework/, never from the store being loaded — a fixture store
    # carries content artifacts only.
    try:
        validator(kind).validate(data)
    except ValidationError as e:
        raise SchemaInvalid(str(path), e.message) from e


@dataclass
class Store:
    root: Path
    _rus: dict[str, Ru] = field(default_factory=dict)
    _feats: dict[str, Feat] = field(default_factory=dict)
    _gaps: dict[str, Gap] = field(default_factory=dict)
    _manifests: dict[str, Manifest] = field(default_factory=dict)
    _models: dict[str, Model] = field(default_factory=dict)
    _intents: list[str] = field(default_factory=list)
    _intent_paths: dict[str, Path] = field(default_factory=dict)
    _adrs: dict[str, Path] = field(default_factory=dict)
    # Framework vocabularies (L10/L12) come from the STORE's spec/framework/ —
    # fixture stores carry their own; JSON Schemas stay repo-level (D-P1.6).
    _tags: list[str] = field(default_factory=list)
    _actors: dict[str, dict] = field(default_factory=dict)
    _aliases: dict[str, str] = field(default_factory=dict)

    # ------------------------------------------------------------ loading

    @classmethod
    def load(cls, root: Path, changed: list[Path] | None = None) -> "Store":
        """Load the store under ``root/spec``. With ``changed``, parse only
        those files (incremental mode for diff-scoped lint runs)."""
        store = cls(root=Path(root))
        spec = store.root / "spec"
        if changed is not None:
            files = sorted(Path(p).resolve() for p in changed)
        else:
            files = sorted(
                p for d in ("ru", "features", "gaps", "manifests", "models", "intent", "rationale")
                if (spec / d).is_dir()
                for p in (spec / d).iterdir()
                if p.is_file() and p.name not in _IGNORED
            )
        for path in files:
            store._ingest(path)
        store._load_framework_vocab(spec / "framework")
        return store

    def _load_framework_vocab(self, framework: Path) -> None:
        tags_file = framework / "tags.yaml"
        if tags_file.is_file():
            self._tags = _load_yaml(tags_file).get("tags") or []
        actors_file = framework / "actors.yaml"
        if actors_file.is_file():
            for entry in _load_yaml(actors_file).get("actors") or []:
                self._actors[entry["id"]] = entry
                for alias in entry.get("aliases", []):
                    self._aliases[alias] = entry["id"]

    def _ingest(self, path: Path) -> None:
        kind = path.parent.name
        name = path.name
        if kind == "ru":
            if not _RU_FILE.match(name):
                raise UnknownArtifact(str(path), "not an RU filename (RU-XXXX.yaml or RU-draft-<ULID>.yaml)")
            data = _load_yaml(path)
            _validate("ru", data, path)
            if data["id"] != path.stem:
                raise FilenameIdMismatch(str(path), f"id {data['id']!r} != filename {path.stem!r}")
            self._rus[data["id"]] = Ru(
                path=path, raw=data, id=data["id"],
                status=data["status"], tier=data.get("tier", "standard"),
            )
        elif kind == "features":
            if not _FEAT_FILE.match(name):
                raise UnknownArtifact(str(path), "not a FEAT filename (FEAT-<slug>.yaml)")
            data = _load_yaml(path)
            _validate("feat", data, path)
            if data["id"] != path.stem:
                raise FilenameIdMismatch(str(path), f"id {data['id']!r} != filename {path.stem!r}")
            self._feats[data["id"]] = Feat(path=path, raw=data, id=data["id"])
        elif kind == "gaps":
            if not _GAP_FILE.match(name):
                raise UnknownArtifact(str(path), "not a GAP filename (GAP-<ULID>.yaml)")
            data = _load_yaml(path)
            _validate("gap", data, path)
            if data["id"] != path.stem:
                raise FilenameIdMismatch(str(path), f"id {data['id']!r} != filename {path.stem!r}")
            self._gaps[data["id"]] = Gap(path=path, raw=data, id=data["id"], severity=data["severity"])
        elif kind == "manifests":
            if not _MANIFEST_FILE.match(name):
                raise UnknownArtifact(str(path), "not a manifest filename (<service>.manifest.yaml)")
            data = _load_yaml(path)
            _validate("manifest", data, path)
            expected = name.removesuffix(".manifest.yaml")
            if data["service"] != expected:
                raise FilenameIdMismatch(str(path), f"service {data['service']!r} != filename {expected!r}")
            self._manifests[data["service"]] = Manifest(
                path=path, raw=data, service=data["service"], content_hash=_sha256(path),
            )
        elif kind == "models":
            if not _MODEL_FILE.match(name):
                raise UnknownArtifact(str(path), "not a model filename (MDL-<id>.statechart.json)")
            data = _load_json(path)
            _validate("model", data, path)
            expected = name.removesuffix(".statechart.json").removeprefix("MDL-")
            if data["id"] != expected:
                raise FilenameIdMismatch(str(path), f"id {data['id']!r} != filename id {expected!r}")
            self._models[data["id"]] = Model(
                path=path, raw=data, id=data["id"], content_hash=_sha256(path),
            )
        elif kind == "intent":
            if not _INT_FILE.match(name):
                raise UnknownArtifact(str(path), "not an INT filename (INT-XXXX.<ext>)")
            self._intents.append(path.stem)
            self._intent_paths[path.stem] = path
        elif kind == "rationale":
            # ADRs are prose, not schema-validated YAML — the store tracks
            # identity and bytes (link fingerprints, §7.3), never structure.
            if not _ADR_FILE.match(name):
                raise UnknownArtifact(str(path), "not an ADR filename (ADR-<slug>.md)")
            self._adrs[path.stem] = path
        else:
            raise UnknownArtifact(str(path), f"file in undeclared store directory {kind!r}")

    # ------------------------------------------------------------ accessors

    def rus(self) -> list[Ru]:
        return [self._rus[k] for k in sorted(self._rus)]

    def features(self) -> list[Feat]:
        return [self._feats[k] for k in sorted(self._feats)]

    def gaps(self) -> list[Gap]:
        return [self._gaps[k] for k in sorted(self._gaps)]

    def manifests(self) -> dict[str, Manifest]:
        return dict(sorted(self._manifests.items()))

    def models(self) -> dict[str, Model]:
        return dict(sorted(self._models.items()))

    def intents(self) -> list[str]:
        return sorted(self._intents)

    def intent_path(self, int_id: str) -> Path | None:
        return self._intent_paths.get(int_id)

    def adrs(self) -> dict[str, Path]:
        return dict(sorted(self._adrs.items()))

    def adr_path(self, adr_id: str) -> Path | None:
        return self._adrs.get(adr_id)

    def tags(self) -> list[str]:
        return list(self._tags)

    def actors(self) -> dict[str, dict]:
        return dict(self._actors)

    def alias_of(self, word: str) -> str | None:
        """Canonical actor id if `word` is a registered alias (L12 rename hint)."""
        return self._aliases.get(word)

    def scope_service(self, ru: Ru) -> str | None:
        """v1 heuristic (plan D-P1.1): the first path segment of the RU's first
        `scope.owns` glob names its service iff a manifest by that name exists.
        Owns-globs are conventionally service-rooted (`service-orders/...`);
        anything else resolves from `shared` only."""
        owns = (ru.raw.get("scope") or {}).get("owns") or []
        if not owns:
            return None
        head = str(owns[0]).split("/", 1)[0]
        return head if head in self._manifests else None

    # ------------------------------------------------------------ resolution

    def resolve_ref(self, token: str, scope: str | None = None) -> Resolved:
        """Resolve a reference token per §5.3 (v0.10).

        Qualified tokens resolve ONLY against the named service's manifest —
        a miss is UnresolvedRef, never a fallback. Unqualified tokens resolve
        against ``scope``'s manifest, then ``shared``. Qualified ``value``
        tokens are malformed (foreign scalars promote to shared)."""
        parsed = parse_one(token)
        if isinstance(parsed, TokenError):
            if parsed.reason == "qualified-value":
                raise MalformedRef(
                    None,
                    f"{token!r}: qualified value refs are forbidden — a foreign scalar "
                    "is the promotion-to-shared trigger (§5.3, §5.5)",
                )
            raise MalformedRef(None, f"malformed reference token {token!r} (formats §2)")
        kind, qualifier, key = parsed.kind, parsed.qualifier, parsed.key
        if qualifier:
            candidates = [qualifier]
        else:
            candidates = [s for s in (scope, "shared") if s]
        for service in candidates:
            manifest = self._manifests.get(service)
            if manifest is None:
                continue
            value = _lookup(manifest.raw, kind, key)
            if value is not None:
                return Resolved(kind=kind, key=key, service=service, value=value)
        raise UnresolvedRef(
            None,
            f"{token!r} does not resolve (searched: {', '.join(candidates) or 'nothing'})",
        )


def _lookup(manifest: dict, kind: str, key: str) -> object | None:
    if kind == "value":
        node: object = manifest.get("values", {})
        for part in key.split("."):
            if not isinstance(node, dict) or part not in node:
                return None
            node = node[part]
        return None if isinstance(node, dict) else node
    if kind == "problem":
        return manifest.get("problem_types", {}).get(key)
    if kind == "audit":
        return next((e for e in manifest.get("audit_events", []) if e.get("code") == key), None)
    if kind == "vocab":
        return manifest.get("vocabularies", {}).get(key)
    if kind == "artifact":
        artifact_id, _, field = key.partition(".")
        artifact = (manifest.get("artifacts") or {}).get(artifact_id)
        if artifact is None or not field:
            return artifact
        return next((f for f in artifact.get("fields") or []
                     if f.get("name") == field), None)
    if kind == "endpoint":
        return _lookup_endpoint(manifest, key)
    if kind in ("message", "channel"):
        section = {"message": "messages", "channel": "channels"}[kind]
        return next((e for e in manifest.get(section, []) if e.get("id") == key), None)
    if kind == "frame":
        channel_id, _, frame_id = key.partition(".")
        if not frame_id or "." in frame_id:
            return None
        channel = next((c for c in manifest.get("channels", []) if c.get("id") == channel_id), None)
        if channel is None:
            return None
        return next((f for f in channel.get("frames", []) if f.get("id") == frame_id), None)
    return None


def _lookup_endpoint(manifest: dict, key: str) -> object | None:
    """Resolve `<id>[.<direction>[.<field-path>]]` against the HTTP surface.

    Each depth resolves to the thing at that depth: the entry, the direction's
    declaration, or one declared field. A direction declared `none` resolves to
    the string `none` — "this surface carries nothing" is a POSITIVE claim, so
    it must resolve; an ABSENT direction does not, which is what lets C10 and
    L15 tell an unfinished declaration from a deliberate empty one."""
    endpoint_id, _, path = key.partition(".")
    entry = next((e for e in manifest.get("endpoints", []) if e.get("id") == endpoint_id), None)
    if entry is None or not path:
        return entry
    direction, _, field_path = path.partition(".")
    slot = entry.get(direction)
    if slot is None:
        return None
    if not field_path:
        return slot
    if not isinstance(slot, dict):
        return None                       # `none`: no field can be addressed inside it
    fields = slot.get("fields")
    if not isinstance(fields, list):
        return None
    return next((f for f in fields if f.get("name") == field_path), None)
