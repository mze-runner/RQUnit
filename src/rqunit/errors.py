"""Typed store errors (TASK-003). One class per failure mode so tests and
lints can assert on the exact error rather than message text."""


class StoreError(Exception):
    """Base class for all spec-store loading and resolution errors."""

    def __init__(self, path: str | None, message: str):
        self.path = path
        super().__init__(f"{path}: {message}" if path else message)


class MalformedYaml(StoreError):
    """Artifact file is not parseable YAML/JSON."""


class SchemaInvalid(StoreError):
    """Artifact parsed but failed its JSON Schema (schema stage, L18-analogue)."""


class FilenameIdMismatch(StoreError):
    """Filename does not match the artifact's `id`/`service` field (feeds L9)."""


class UnknownArtifact(StoreError):
    """File in a store directory that matches no artifact naming convention."""


class BadConfig(StoreError):
    """rqunit.toml is unparseable or carries unknown tables/keys — a typo
    silently ignored would read as configured, so strictness is the kindness."""


class MalformedRef(StoreError):
    """Reference token violates the grammar (formats §2): unknown kind, empty
    key, nesting, or a qualified `value` ref (foreign scalars promote to
    shared, spec §5.3)."""


class UnresolvedRef(StoreError):
    """Well-formed reference token that resolves to no manifest fact (L15).
    Qualified refs resolve only against the named manifest — never a
    fallback (spec §5.3 v0.10)."""
