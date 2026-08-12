"""`rqunit init` — adoption. The invariant that matters is not which files
appear but that what appears is a store the rest of the toolchain accepts:
it loads, it lints clean, and its configuration parses under the strict
reader. Asserting a file census here would pin the layout twice."""

from pathlib import Path

from click.testing import CliRunner

from rqunit import config
from rqunit.cli.init import main as init_main
from rqunit.cli.rqunit import main as rqunit
from rqunit.schemas import SPEC_VERSION, installed_version, store_pack_version
from rqunit.store import Store


def _init(root: Path, *args):
    return CliRunner().invoke(init_main, ["--store", str(root), *args])


def test_scaffolded_store_loads_and_passes_the_gates(tmp_path):
    assert _init(tmp_path).exit_code == 0
    Store.load(tmp_path)  # the loader is the acceptance test for the layout
    for verb in ("lint", "check", "doctor"):
        result = CliRunner().invoke(rqunit, [verb, "--store", str(tmp_path)])
        assert result.exit_code == 0, f"{verb}: {result.output}"


def test_seeded_vocabularies_are_the_packs_own(tmp_path):
    _init(tmp_path)
    spec = tmp_path / "spec"
    for seeded in ("framework/tags.yaml", "framework/actors.yaml",
                   "framework/coverage.policy.yaml", "manifests/shared.manifest.yaml"):
        assert (spec / seeded).is_file(), seeded
    from rqunit.schemas import SEED_DIR
    assert (spec / "framework" / "tags.yaml").read_text() == (SEED_DIR / "tags.yaml").read_text()


def test_the_seeded_segment_registry_declares_nothing(tmp_path):
    """The one identity decision a store cannot revisit was previously reached by
    omission: no file, no segments, permanent ids, and nothing anywhere telling
    the consumer a decision was being made. The seed exists to disclose it, so
    the invariant is that it discloses WITHOUT deciding — a scaffolded store has
    no segments, exactly as before."""
    from rqunit.segments import declared, load_segments

    _init(tmp_path)

    assert (tmp_path / "spec" / "framework" / "segments.yaml").is_file()
    assert load_segments(tmp_path) == []
    assert declared(tmp_path) == set()


def test_deleting_the_seeded_registry_changes_no_report(tmp_path):
    """Byte-identical in effect to an absent file, or every existing store
    changes meaning on upgrade. Reports are compared rather than the loader,
    because the loader agreeing is not the same claim as the tools agreeing."""
    from rqunit.checks.base import run_checks
    from rqunit.lints.base import run_lints

    _init(tmp_path)
    seeded = (run_lints(Store.load(tmp_path)), run_checks(Store.load(tmp_path)))

    (tmp_path / "spec" / "framework" / "segments.yaml").unlink()

    assert (run_lints(Store.load(tmp_path)), run_checks(Store.load(tmp_path))) == seeded


def test_init_names_the_runtime_files_it_wrote(tmp_path):
    """These land in a directory the consumer also authors in, and `.claude/` is
    commonly gitignored — so a count alone left no way to reconstruct what
    arrived. An existing file is never overwritten and the skipped set was
    already reported; what was missing was the names on the way in."""
    result = _init(tmp_path)

    assert result.exit_code == 0
    assert ".claude/skills/ru-authoring/SKILL.md" in result.output
    assert ".claude/hooks/h1-scope-guard.sh" in result.output


def test_init_never_overwrites_a_runtime_file_and_says_which_it_kept(tmp_path):
    """The guarantee is by design, not by filename luck: a scaffold that silently
    replaced someone's edited hook is a scaffold nobody runs twice."""
    hook = tmp_path / ".claude" / "hooks" / "h1-scope-guard.sh"
    hook.parent.mkdir(parents=True)
    hook.write_text("# mine\n")

    result = _init(tmp_path)

    assert hook.read_text() == "# mine\n", "an existing file is never touched"
    assert "already existed — left untouched" in result.output
    assert "--refresh-integrations" in result.output       # names the way to overwrite


def test_a_scaffolded_store_says_it_holds_no_requirements(tmp_path):
    """An empty store used to produce output byte-identical in spirit to a mature
    healthy one, from every command in the product. Visible debt is by design and
    status belongs in tool output — and an empty store is the largest debt there
    is. Finding-class, so the exit code stays 0: nothing is WRONG on day one."""
    _init(tmp_path)

    for verb in ("lint", "check"):
        result = CliRunner().invoke(rqunit, [verb, "--store", str(tmp_path), "--format", "text"])
        assert result.exit_code == 0, result.output
        assert "holds no requirements" in result.output, verb
        assert "STORE/finding" in result.output, verb

    doctor = CliRunner().invoke(rqunit, ["doctor", "--store", str(tmp_path)])
    assert doctor.exit_code == 0
    assert "holds no requirements" in doctor.output
    assert "structurally sound" not in doctor.output


def test_the_empty_store_finding_stops_once_a_requirement_exists():
    """It must be resolvable, or it is the kind of note that teaches people to
    skim the tool. Keyed on "no RUs at all" and not on any count, because a
    threshold would pin point-in-time state."""
    from rqunit.doctor import empty_store
    from rqunit.violations import empty_store_findings

    populated = Store.load(Path(__file__).parent.parent / "fixtures" / "store" / "valid")

    assert empty_store_findings(populated) == []
    assert empty_store(populated) == []


def test_pack_pin_records_the_spec_version_not_the_tool_version(tmp_path):
    """The pin names the VOCABULARY a store was authored in. It recorded the
    package version until v0.14, and the two had drifted a minor apart — so a
    store was pinned to a specification version that was never published."""
    _init(tmp_path)
    assert store_pack_version(tmp_path) == SPEC_VERSION


def test_unpinned_store_falls_back_to_this_build_s_spec_version(tmp_path):
    """A store predating the pin is unpinned, not broken: reporting the
    enforcing vocabulary beats reporting nothing."""
    _init(tmp_path)
    (tmp_path / "spec" / "framework" / "pack.yaml").unlink()
    assert store_pack_version(tmp_path) == SPEC_VERSION


def test_the_two_versions_are_reported_separately(tmp_path):
    """Not a discrepancy to reconcile — a tool fix changes no vocabulary, so
    `tool_version` and `framework_version` are different questions."""
    _init(tmp_path)
    assert installed_version()                    # the package doing the enforcing
    assert store_pack_version(tmp_path)           # the vocabulary being enforced


def test_rust_detection_writes_config_the_strict_reader_accepts(tmp_path):
    (tmp_path / "Cargo.toml").write_text("[package]\nname = \"app\"\n")
    result = _init(tmp_path)
    assert result.exit_code == 0 and "rust" in result.output
    loaded = config.load(tmp_path)
    # parsed, not defaulted past a bad file
    assert loaded.stack("rust").options["conformance_crate"]


def test_stackless_detection_writes_no_stacks_table(tmp_path):
    """A detected stack with no adapter must not produce a [stacks] table the
    reader would reject — the store has to work before the language does."""
    (tmp_path / "pom.xml").write_text("<project/>")
    result = _init(tmp_path)
    assert result.exit_code == 0 and "jvm" in result.output
    written = (tmp_path / "rqunit.toml").read_text()
    assert not [ln for ln in written.splitlines() if ln.strip().startswith("[")]
    assert config.load(tmp_path) == config.Config()


def test_stack_override_beats_detection(tmp_path):
    (tmp_path / "pom.xml").write_text("<project/>")
    result = _init(tmp_path, "--stack", "rust")
    assert result.exit_code == 0
    assert config.load(tmp_path).stack("rust").options["trace_scan"]


def test_refuses_a_non_empty_store_without_touching_it(tmp_path):
    ru = tmp_path / "spec" / "ru"
    ru.mkdir(parents=True)
    (ru / "RU-0001.yaml").write_text("id: RU-0001\n")
    result = _init(tmp_path)
    assert result.exit_code == 1
    assert (ru / "RU-0001.yaml").read_text() == "id: RU-0001\n"
    assert not (tmp_path / "spec" / "framework").exists()


def test_existing_config_is_never_overwritten(tmp_path):
    (tmp_path / "Cargo.toml").write_text("[package]\nname = \"app\"\n")
    original = "[stacks.rust]\nconformance_crate = \"mine\"\n"
    (tmp_path / "rqunit.toml").write_text(original)
    assert _init(tmp_path).exit_code == 0
    assert (tmp_path / "rqunit.toml").read_text() == original


def test_the_scaffold_mentions_every_key_the_toolchain_reads(tmp_path):
    """`audit` was accepted by config.py, read by the Rust probe, and depended
    on by CF10/CF11 — and absent from the scaffold, so a consumer had no way to
    discover it existed. A key you cannot find in the file you configure is a
    capability that silently does nothing. Core-read keys are DERIVED from
    config.py so a new accepted key nobody documented fails this build; the
    adapter-owned list genuinely cannot be derived until adapter manifests
    exist (it becomes the manifest's config_keys then), so it is literal."""
    from rqunit.config import ROLES, _CORE_KEYS

    core_read = tuple(sorted((_CORE_KEYS - {"adapter"}) | set(ROLES) | {"manifest"}))
    adapter_owned = ("trace_scan", "conformance_crate", "service",
                     "routers", "messages", "audit")

    (tmp_path / "Cargo.toml").write_text('[package]\nname = "app"\n')
    _init(tmp_path)
    scaffold = (tmp_path / "rqunit.toml").read_text()
    # The TOML forms, not a bare substring: "audit" appears in the prose that
    # explains the block, so a substring check passes with the key deleted —
    # a test that looks like proof and is not.
    missing = [name for name in (*core_read, *adapter_owned)
               if f"{name} =" not in scaffold
               and f"[stacks.rust.{name}]" not in scaffold]
    assert missing == [], f"accepted but undiscoverable: {', '.join(missing)}"


def test_the_scaffold_it_writes_is_one_the_strict_reader_accepts(tmp_path):
    """Unknown keys are errors, so a scaffold with a typo would make `init`
    produce a store its own loader rejects."""
    (tmp_path / "Cargo.toml").write_text('[package]\nname = "app"\n')
    _init(tmp_path)
    stack = config.load(tmp_path).stack("rust")
    assert stack.options["trace_scan"] and stack.options["conformance_crate"]
    assert stack.adapter.extractor.artifact     # the extractor role is declared


def test_emitted_guidance_names_only_directories_the_store_has():
    """The skills and agents `init` writes into a consumer repository are read
    by agents BEFORE they touch the store, so a directory named there that the
    layout does not have is an instruction to create one — which the loader
    then rejects. This is how the retired contract kind survived its own
    removal: the schema, the rules and the docs dropped `spec/contracts/`, and
    the emitted authoring skill went on telling every new consumer to write
    there. Assert against STORE_DIRS, the layout's single source."""
    import re

    from rqunit.cli.init import STORE_DIRS

    root = Path(__file__).parent.parent / "src" / "rqunit" / "integrations"
    named = re.compile(r"spec/(?:\{([a-z,_.-]+)\}|([a-z_-]+))/")

    stray = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in {".md", ".sh", ".json", ".yaml"}:
            continue
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            for m in named.finditer(line):
                group = m.group(1) or m.group(2)
                for name in group.split(","):
                    if name.strip() and name.strip() not in STORE_DIRS:
                        stray.append(f"{path.name}:{lineno} names spec/{name.strip()}/")
    assert not stray, (
        "emitted guidance names directories the scaffold never creates:\n  "
        + "\n  ".join(stray)
    )


def test_agent_templates_land_in_the_consumer_runtime(tmp_path):
    """Guidance the tool ships but never installs is guidance that drifts: the
    retired contract kind survived its own removal for exactly as long as these
    files were hand-copied. Emission is what makes them the tool's problem."""
    from rqunit.cli.init import INTEGRATION_DIR

    assert _init(tmp_path).exit_code == 0
    shipped = {p.relative_to(INTEGRATION_DIR / "claude-code")
               for p in (INTEGRATION_DIR / "claude-code").rglob("*") if p.is_file()}
    assert shipped, "no templates ship — this test would pass vacuously"
    for relative in shipped:
        assert (tmp_path / ".claude" / relative).is_file(), f"{relative} was not emitted"


def test_emitted_hooks_stay_executable(tmp_path):
    """A hook that arrives without its executable bit fails in the one way that
    looks like the guard passing."""
    _init(tmp_path)
    hooks = list((tmp_path / ".claude" / "hooks").glob("*.sh"))
    assert hooks
    for hook in hooks:
        assert hook.stat().st_mode & 0o111, f"{hook.name} is not executable"


def test_adoption_never_overwrites_the_consumers_own_runtime_files(tmp_path):
    """`.claude/` is a directory the consumer also authors in. A scaffold that
    replaces someone's edited agent is a scaffold nobody runs twice."""
    mine = tmp_path / ".claude" / "agents" / "requirements-analyst.md"
    mine.parent.mkdir(parents=True)
    mine.write_text("my own agent\n")

    result = _init(tmp_path)
    assert result.exit_code == 0
    assert mine.read_text() == "my own agent\n"
    assert "left untouched" in result.output
    assert (tmp_path / ".claude" / "skills" / "spec-store" / "SKILL.md").is_file()


def test_refresh_rewrites_templates_and_touches_nothing_else(tmp_path):
    """The upgrade path. It must work on a store that already exists — which is
    the whole point, since `init` refuses to scaffold over one."""
    _init(tmp_path)
    skill = tmp_path / ".claude" / "skills" / "spec-store" / "SKILL.md"
    shipped = skill.read_text()
    skill.write_text("stale copy\n")
    pack = tmp_path / "spec" / "framework" / "pack.yaml"
    before = pack.read_text()

    result = _init(tmp_path, "--refresh-integrations")
    assert result.exit_code == 0
    assert skill.read_text() == shipped
    assert pack.read_text() == before


def test_a_freshly_scaffolded_store_passes_the_currency_gate(tmp_path):
    """A scaffold whose very next gate is red teaches people the gate is noise.
    Projections are committed and currency-checked, so a store that has never
    generated is reported as out of date — which made `rqunit generate check`
    fail on a store the operator had done nothing to but create."""
    from rqunit.cli.generate import main as generate_main

    assert _init(tmp_path).exit_code == 0
    result = CliRunner().invoke(generate_main, ["check", "--store", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert list((tmp_path / "spec" / "projections").glob("*.json")), \
        "nothing was generated — the gate passed vacuously"
