"""Adapter invocation — the seam where core execs a declared adapter command
or reads its artifact. Invariants: both transports produce the same validated
observation; the stdio exit contract (0 ok / 1 probe failure / 2 tool error)
maps to teaching errors, never silence; an unsupported contract_version is
named, not guessed across; an absent role is RoleUnavailable, not a skip; and
the adapter manifest is the vocabulary authority for passthrough keys."""

import json
import shutil
import sys
from pathlib import Path

import pytest

from click.testing import CliRunner

from rqunit.config import Adapter, Role, Stack
from rqunit.doctor import stack_config_health
from rqunit.errors import BadConfig, RoleUnavailable
from rqunit.invoke import load_adapter_manifest, run_role, stack_declaration_problems

FIXTURES = Path(__file__).parent.parent / "fixtures"

ARTIFACT = {"contract_version": 1, "generated_by": "fake-probe 0.1",
            "services": {"service-orders": {"endpoints": []}}}

SCHEMA = "actual-surface.schema.json"


def _stack(**adapter_kwargs) -> Stack:
    return Stack(name="rust", adapter=Adapter(**adapter_kwargs))


def _probe(tmp_path: Path, body: str) -> Role:
    script = tmp_path / "probe.py"
    script.write_text(body)
    return Role(cmd=(sys.executable, str(script)))


def test_cmd_mode_returns_the_validated_observation(tmp_path):
    role = _probe(tmp_path, f"""
import json, sys
if "--root" not in sys.argv:
    sys.exit(3)
print(json.dumps({ARTIFACT!r}))
""")
    data = run_role(tmp_path, _stack(extractor=role), "extractor", schema=SCHEMA)
    assert data == ARTIFACT


def test_artifact_mode_yields_the_same_observation(tmp_path):
    (tmp_path / "actual-surface.json").write_text(json.dumps(ARTIFACT))
    stack = _stack(extractor=Role(artifact="actual-surface.json"))
    assert run_role(tmp_path, stack, "extractor", schema=SCHEMA) == ARTIFACT


def test_relative_cmd_resolves_against_the_consumer_root(tmp_path):
    script = tmp_path / "probe.sh"
    script.write_text(f"#!/bin/sh\necho '{json.dumps(ARTIFACT)}'\n")
    script.chmod(0o755)
    stack = _stack(extractor=Role(cmd=("probe.sh",)))
    assert run_role(tmp_path, stack, "extractor", schema=SCHEMA) == ARTIFACT


def test_probe_failure_surfaces_the_adapters_stderr(tmp_path):
    role = _probe(tmp_path, 'import sys; print("cannot parse router", file=sys.stderr); sys.exit(1)')
    with pytest.raises(BadConfig) as caught:
        run_role(tmp_path, _stack(extractor=role), "extractor", schema=SCHEMA)
    assert "probe failure" in str(caught.value) and "cannot parse router" in str(caught.value)


def test_tool_error_exit_is_distinguished_from_probe_failure(tmp_path):
    role = _probe(tmp_path, "import sys; sys.exit(3)")
    with pytest.raises(BadConfig) as caught:
        run_role(tmp_path, _stack(extractor=role), "extractor", schema=SCHEMA)
    assert "tool error" in str(caught.value)


def test_unparseable_stdout_is_an_error_naming_the_channel_contract(tmp_path):
    role = _probe(tmp_path, 'print("log line, not an artifact")')
    with pytest.raises(BadConfig) as caught:
        run_role(tmp_path, _stack(extractor=role), "extractor", schema=SCHEMA)
    assert "stderr" in str(caught.value)      # teaches where logs belong


def test_unsupported_contract_version_is_named_never_guessed_across(tmp_path):
    artifact = dict(ARTIFACT, contract_version=2)
    role = _probe(tmp_path, f"import json\nprint(json.dumps({artifact!r}))")
    with pytest.raises(BadConfig) as caught:
        run_role(tmp_path, _stack(extractor=role), "extractor", schema=SCHEMA)
    assert "contract_version" in str(caught.value) and "1" in str(caught.value)


def test_schema_violations_name_the_contract(tmp_path):
    artifact = {"contract_version": 1, "services": {}}          # generated_by missing
    role = _probe(tmp_path, f"import json\nprint(json.dumps({artifact!r}))")
    with pytest.raises(BadConfig) as caught:
        run_role(tmp_path, _stack(extractor=role), "extractor", schema=SCHEMA)
    assert "actual-surface contract" in str(caught.value)


def test_an_absent_role_is_unavailable_never_silently_skipped(tmp_path):
    with pytest.raises(RoleUnavailable) as caught:
        run_role(tmp_path, _stack(), "extractor", schema=SCHEMA)
    assert "declares no extractor" in str(caught.value)


def test_a_missing_binary_names_both_fixes(tmp_path):
    stack = _stack(extractor=Role(cmd=("./does-not-exist",)))
    with pytest.raises(BadConfig) as caught:
        run_role(tmp_path, stack, "extractor", schema=SCHEMA)
    message = str(caught.value)
    assert "build the adapter" in message and "artifact" in message


# ------------------------------------------------------------ adapter manifest

MANIFEST = """\
contract_version: 1
stack: rust
roles: [extractor]
config_keys: [trace_scan, service]
"""


def test_manifest_loads_from_the_declared_path(tmp_path):
    (tmp_path / "adapter.yaml").write_text(MANIFEST)
    stack = Stack(name="rust", adapter=Adapter(manifest="adapter.yaml"))
    manifest = load_adapter_manifest(tmp_path, stack)
    assert manifest["roles"] == ["extractor"]


def test_manifest_defaults_to_the_adapters_conventional_home(tmp_path):
    home = tmp_path / "adapters" / "rust"
    home.mkdir(parents=True)
    (home / "adapter.yaml").write_text(MANIFEST)
    assert load_adapter_manifest(tmp_path, _stack()) is not None
    assert load_adapter_manifest(tmp_path, Stack(name="jvm")) is None


def test_a_declared_manifest_that_resolves_to_nothing_is_an_error(tmp_path):
    stack = Stack(name="rust", adapter=Adapter(manifest="missing.yaml"))
    with pytest.raises(BadConfig):
        load_adapter_manifest(tmp_path, stack)


def test_a_manifest_wired_to_the_wrong_stack_is_an_error(tmp_path):
    (tmp_path / "adapter.yaml").write_text(MANIFEST.replace("stack: rust", "stack: jvm"))
    stack = Stack(name="rust", adapter=Adapter(manifest="adapter.yaml"))
    with pytest.raises(BadConfig) as caught:
        load_adapter_manifest(tmp_path, stack)
    assert "wrong stack" in str(caught.value)


def test_manifest_is_the_typo_detector_for_passthrough_keys(tmp_path):
    """The typo'd key is named; the key the adapter does read is not."""
    (tmp_path / "adapter.yaml").write_text(MANIFEST)
    stack = Stack(name="rust",
                  adapter=Adapter(manifest="adapter.yaml"),
                  options={"trace_scam": ["x"], "service": "service-orders"})
    problems = stack_declaration_problems(tmp_path, stack)
    assert any("trace_scam" in p for p in problems)
    assert not any("'service'" in p or "service," in p for p in problems)


def test_manifest_catches_a_declared_role_the_adapter_does_not_ship(tmp_path):
    (tmp_path / "adapter.yaml").write_text(MANIFEST)
    stack = Stack(name="rust", adapter=Adapter(
        manifest="adapter.yaml", scanner=Role(cmd=("scan",))))
    problems = stack_declaration_problems(tmp_path, stack)
    assert any("scanner" in p for p in problems)
    assert not any("extractor" in p for p in problems)   # the shipped role is fine


# ------------------------------------------------------------ doctor surfacing

def test_doctor_says_when_a_whole_config_table_is_unchecked(tmp_path):
    """Core deliberately never interprets passthrough keys, so without a
    manifest NOTHING validates them and a typo reads as configured. The stack
    here is one this build ships no adapter for — the only case where the note
    is still true, and the case it must name a real source of a manifest for."""
    (tmp_path / "rqunit.toml").write_text('[stacks.jvm]\nsome_key = ["x"]\n')
    findings = [f for f in stack_config_health(tmp_path) if f.kind == "stack-config"]
    assert len(findings) == 1 and findings[0].severity == "info"
    assert "some_key" in findings[0].message
    assert "manifest" in findings[0].suggestion


def test_a_first_party_stack_validates_its_keys_with_nothing_wired(tmp_path):
    """The note used to fire here, instructing the reader to point `manifest`
    at a file that existed only inside this repository — well written, and
    terminating in a dead end. A first-party adapter's manifest ships in the
    pack, so the keys are validated with no wiring and there is nothing to
    report."""
    (tmp_path / "rqunit.toml").write_text('[stacks.rust]\ntrace_scan = ["x"]\n')
    assert [f for f in stack_config_health(tmp_path) if f.kind == "stack-config"] == []


def test_a_typo_is_caught_against_the_bundled_manifest(tmp_path):
    """The point of shipping it: the vocabulary authority is present, so a
    misspelled passthrough key is named instead of reading as configured. And the
    remedy offered has to be one the reader can perform — a bundled manifest sits
    inside the installed package, so "add the key to its config_keys" would be
    the same dead end this finding was about."""
    (tmp_path / "rqunit.toml").write_text('[stacks.rust]\ntrace_scam = ["x"]\n')
    findings = [f for f in stack_config_health(tmp_path) if f.kind == "stack-config"]

    named = [f for f in findings if f.severity == "warning" and "trace_scam" in f.message]
    assert named
    assert "config_keys" not in named[0].message


def test_doctor_says_nothing_about_a_stack_with_nothing_to_validate(tmp_path):
    """A stack declaring no passthrough keys loses nothing by having no
    manifest. A note whose subject is empty is the noise that teaches people to
    skim doctor, which costs more than the note earns."""
    (tmp_path / "rqunit.toml").write_text(
        '[stacks.rust]\nliteral_scan = ["**/tests/*.rs"]\n'
        '[stacks.rust.adapter]\nextractor = { artifact = "surface.json" }\n')
    assert stack_config_health(tmp_path) == []


def test_doctor_warns_on_keys_the_adapter_does_not_read(tmp_path):
    (tmp_path / "adapter.yaml").write_text(MANIFEST)
    (tmp_path / "rqunit.toml").write_text(
        '[stacks.rust]\ntrace_scam = ["x"]\n'
        '[stacks.rust.adapter]\nmanifest = "adapter.yaml"\n')
    findings = [f for f in stack_config_health(tmp_path) if f.kind == "stack-config"]
    assert any(f.severity == "warning" and "trace_scam" in f.message for f in findings)


# ------------------------------------------------------------ conformance wiring

def test_conformance_runs_a_cmd_mode_extractor_end_to_end(tmp_path):
    from rqunit.cli.conformance import main as conformance_main

    root = tmp_path / "repo"
    shutil.copytree(FIXTURES / "store" / "valid", root)
    script = root / "probe.py"
    script.write_text(f"import json\nprint(json.dumps({ARTIFACT!r}))")
    (root / "rqunit.toml").write_text(
        '[stacks.rust.adapter]\n'
        f'extractor = {{ cmd = ["{sys.executable}", "probe.py"] }}\n')
    result = CliRunner().invoke(conformance_main, ["--store", str(root)])
    assert result.exit_code in (0, 1), result.output       # judged, not tool-errored
    report = json.loads(result.output)
    # The store's declared boundary reached provenance: the valid fixture
    # declares endpoints, so a probe-fed run counts a non-empty boundary.
    assert report["boundary"]["endpoints"] > 0
    assert report["summary"]["checked_files"] == 1         # exactly the declared probe
    # Violations from a cmd probe are attributed to the declaration site an
    # operator can act on, never to another probe's file.
    for violation in report["violations"]:
        assert "probe.py" not in violation.get("path", "")
        assert "[stacks.rust.adapter] extractor" in violation.get("path", "")


# ------------------------------------- consumer wiring (onboarding findings)

def test_a_rejected_config_is_a_violation_on_every_verb(tmp_path):
    """One fact, one category. A config the loader rejects is the STORE being
    wrong; reporting it as a tool error on some verbs sent CI looking for a
    broken rqunit instead of a one-line fix in the consumer's own file."""
    from click.testing import CliRunner

    from rqunit.cli.conformance import main as conformance_main
    from rqunit.cli.lint import main as lint_main
    from rqunit.cli.trace import main as trace_main

    root = tmp_path / "store"
    shutil.copytree(FIXTURES / "store" / "valid", root)
    (root / "rqunit.toml").write_text(
        '[stacks.rust.adapter]\nactual_surface = "x.json"\n')     # retired, now unknown here

    runner = CliRunner()
    for main, args in ((lint_main, ["--store", str(root)]),
                       (trace_main, ["--store", str(root), "--no-write"]),
                       (conformance_main, ["--store", str(root)])):
        result = runner.invoke(main, args)
        assert result.exit_code == 1, f"{main.name}: {result.exit_code}\n{result.output}"
        assert "CONFIG" in result.output


def test_a_retired_key_is_named_with_where_it_went(tmp_path):
    """Core cannot judge adapter passthrough — but it CAN recognise a key it
    used to own. Left in place, such a key loads cleanly and configures
    nothing, which reads to its author as a live setting."""
    from click.testing import CliRunner

    from rqunit.cli.lint import main as lint_main

    root = tmp_path / "store"
    shutil.copytree(FIXTURES / "store" / "valid", root)
    (root / "rqunit.toml").write_text(
        '[stacks.rust]\nactual_surface = "spec-conformance-tests/actual-surface.json"\n')

    result = CliRunner().invoke(lint_main, ["--store", str(root), "--format", "text"])
    assert "actual_surface is retired" in result.output
    assert "extractor = { artifact" in result.output          # names the successor
    assert result.exit_code == 0                              # warning, not blocking


def test_a_retired_key_with_nowhere_to_go_is_not_told_to_move(tmp_path):
    """Retirement has two shapes. A key that simply died must not be wrapped
    in relocation phrasing — "Move it: deleted" sends a reader hunting for a
    destination that does not exist, and this is the one message a consumer
    meets at upgrade with no context but the sentence."""
    from click.testing import CliRunner

    from rqunit.cli.lint import main as lint_main

    root = tmp_path / "store"
    shutil.copytree(FIXTURES / "store" / "valid", root)
    (root / "rqunit.toml").write_text('[stacks.rust]\ntrace_diff = ["*/tests/*.rs"]\n')

    result = CliRunner().invoke(lint_main, ["--store", str(root), "--format", "text"])
    suggestion = next(line for line in result.output.splitlines()
                      if "suggestion:" in line and "trace_diff" not in line)
    assert "Delete it" in suggestion and "nowhere to move" in suggestion
    assert "Move it" not in suggestion


def test_every_retired_key_carries_a_whole_instruction():
    """The values are complete sentences, not fragments a template wraps —
    that is what lets the two shapes coexist. A new entry that returns to a
    fragment reintroduces the mismatch this test exists for."""
    from rqunit.config import RETIRED_KEYS

    assert RETIRED_KEYS
    for key, instruction in RETIRED_KEYS.items():
        assert instruction[0].isupper(), f"{key}: not a sentence"
        assert instruction.rstrip().endswith("."), f"{key}: not a sentence"
        assert "Delete it" in instruction or "delete the old key" in instruction, (
            f"{key}: an instruction for a dead key must say to remove it")


def test_doctor_reports_a_declared_role_that_resolves_nowhere(tmp_path):
    """`adapter verify` proves an ADAPTER correct; nothing proved a CONSUMER
    wired one correctly. A cmd path that resolves on its author's machine and
    nowhere else is committed breakage every other developer meets late."""
    from rqunit.doctor import role_wiring

    (tmp_path / "rqunit.toml").write_text(
        '[stacks.rust.adapter]\nscanner = { cmd = ["../elsewhere/scan-checks"] }\n')
    findings = role_wiring(tmp_path)
    assert len(findings) == 1
    assert findings[0].kind == "role-wiring" and findings[0].severity == "warning"
    assert "scanner" in findings[0].message


def test_doctor_stays_quiet_about_artifact_roles_and_resolvable_commands(tmp_path):
    """An artifact its pipeline has not produced yet is normal, and the verb
    that needs it says so precisely — doctor crying wolf about it is how a
    health check gets ignored. A command that DOES resolve is simply fine."""
    from rqunit.doctor import role_wiring

    (tmp_path / "probe").write_text("#!/bin/sh\n")
    (tmp_path / "probe").chmod(0o755)
    (tmp_path / "rqunit.toml").write_text(
        '[stacks.rust.adapter]\n'
        'extractor = { artifact = "never-generated-yet.json" }\n'
        'scanner = { cmd = ["probe"] }\n')
    assert role_wiring(tmp_path) == []


# ------------------------------------------------------- permanent-id ceiling

class _FakeRu:
    def __init__(self, rid): self.id = rid


class _FakeStore:
    """Both numbered families, independently positioned. RU is allocated per
    segment and in base-32; INT is still the decimal four-digit family, which
    is why the two are positioned against different ceilings."""
    def __init__(self, ru_top=1, int_top=1, segment=None):
        self._ru, self._int, self._segment = ru_top, int_top, segment
    def rus(self):
        from rqunit import ids
        return [_FakeRu(ids.format_id("RU", self._segment, self._ru))]
    def intents(self): return [f"INT-{self._int:04d}"]


def test_doctor_warns_with_runway_before_the_id_ceiling():
    """Widening the sequence width is a store-wide migration, so the only useful
    moment to hear about it is well before the sitting that needs it."""
    from rqunit import ids
    from rqunit.doctor import _HEADROOM_WARN, id_headroom
    from rqunit.store import ID_CEILING

    far_ru = ids.SEQ_CEILING - _HEADROOM_WARN - 1
    far_int = ID_CEILING - _HEADROOM_WARN - 1
    assert id_headroom(_FakeStore(ru_top=far_ru, int_top=far_int)) == []       # quiet

    findings = id_headroom(_FakeStore(ru_top=ids.SEQ_CEILING - 1, int_top=far_int))
    assert len(findings) == 1 and findings[0].kind == "id-headroom"
    assert "1 id(s) left" in findings[0].message
    assert "migration" in findings[0].suggestion


def test_headroom_is_measured_per_segment_because_allocation_is():
    """Each segment is its own sequence, so a store can be comfortable overall
    and out of room in one domain. Measuring the store as a whole would report
    runway that the sitting cannot actually use."""
    from rqunit import ids
    from rqunit.doctor import id_headroom

    findings = id_headroom(_FakeStore(ru_top=ids.SEQ_CEILING - 1, segment="ORD"))
    assert len(findings) == 1
    assert "segment ORD" in findings[0].message
    assert "RU-ORD-" in findings[0].message
    assert "another segment" in findings[0].suggestion, (
        "the nearest fix is a different segment, not a width migration")


def test_doctor_warns_for_decimal_intents_and_names_the_way_out():
    """The gap in the first version of this warning: it watched RU only, so a
    store could sail into the INT ceiling while being told its runway was
    healthy. Intents differ in kind — no verb allocates them, so unlike
    activation nothing will refuse, and the message must not imply otherwise.

    What it must now also do is name a fix. It had none while intents were
    decimal-only; a capture can be a ULID, so the wall is escapable without
    renaming anything."""
    from rqunit import ids
    from rqunit.doctor import _HEADROOM_WARN, id_headroom
    from rqunit.store import ID_CEILING

    far = ids.SEQ_CEILING - _HEADROOM_WARN - 1
    findings = id_headroom(_FakeStore(ru_top=far, int_top=ID_CEILING - 3))
    assert len(findings) == 1
    assert "3 decimal INT id(s) left" in findings[0].message
    assert "ULID" in findings[0].suggestion
    assert "NOTHING allocates" in findings[0].suggestion
    assert "refuses at the ceiling" not in findings[0].suggestion   # RU's guard, not INT's


def test_a_ulid_intent_is_never_counted_into_a_ceiling():
    """A ULID has no ordinal, so folding one into a headroom calculation would
    be a category error — and would report a wall in front of the one family
    that does not have one."""
    from rqunit.doctor import id_headroom

    class _Ulids:
        def rus(self): return []
        def intents(self): return ["INT-01J3F8KQZ2ABCDEFGHJKMNPQRS",
                                   "INT-01J3F8KQZ2ABCDEFGHJKMNPQRT"]
    assert id_headroom(_Ulids()) == []


def test_both_families_are_reported_independently():
    from rqunit import ids
    from rqunit.doctor import id_headroom
    from rqunit.store import ID_CEILING

    findings = id_headroom(_FakeStore(ru_top=ids.SEQ_CEILING - 2,
                                      int_top=ID_CEILING - 5))
    assert len(findings) == 2
    assert any("INT" in f.message for f in findings)
    assert any("unsegmented space" in f.message for f in findings)


def test_the_encoder_refuses_the_ceiling_rather_than_padding_past_it():
    """The decimal scheme's hazard was that `f"{n:04d}"` pads but never
    truncates, so an over-ceiling number rendered as a plausible id and only the
    schema caught it — at the END of a sitting, as "unknown artifact". Base-32
    encoding closes that class by construction: there is no spelling for a
    number past the ceiling, so the refusal happens in arithmetic, before
    anything is written."""
    import pytest

    from rqunit import ids

    assert ids.encode(ids.SEQ_CEILING) == "Z" * ids.SEQ_WIDTH
    with pytest.raises(ValueError):
        ids.encode(ids.SEQ_CEILING + 1)
