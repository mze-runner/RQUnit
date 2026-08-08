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
    """A configuration file is unparseable or carries unknown tables/keys —
    `rqunit.toml`, or one of the consumer-owned registries under
    `spec/framework/`. A typo silently ignored would read as configured, so
    strictness is the kindness."""


class MalformedRef(StoreError):
    """Reference token violates the grammar (formats §2): unknown kind, empty
    key, nesting, or a qualified `value` ref (foreign scalars promote to
    shared, spec §5.3)."""


class UnresolvedRef(StoreError):
    """Well-formed reference token that resolves to no manifest fact (L15).
    Qualified refs resolve only against the named manifest — never a
    fallback (spec §5.3 v0.10)."""


class RoleUnavailable(StoreError):
    """A caller needed an adapter role the stack does not declare. Absence is
    a capability statement, not an error in itself — but whatever needed the
    role reports it rather than silently skipping."""


class DialectViolation(StoreError):
    """A model breaks a statechart dialect rule the generated suite depends
    on (M2/M3/M6). A distinct class because it is a SPEC-CONTENT violation,
    not a tool failure: `lint` reports it as a violation and so must every
    other surface, or CI reads the same fact as 'rqunit is broken' on one
    command and 'your model is wrong' on another."""
