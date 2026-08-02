"""`rqunit init` — adoption. The invariant that matters is not which files
appear but that what appears is a store the rest of the toolchain accepts:
it loads, it lints clean, and its configuration parses under the strict
reader. Asserting a file census here would pin the layout twice."""

from pathlib import Path

from click.testing import CliRunner

from rqunit import config
from rqunit.cli.init import main as init_main
from rqunit.cli.rqunit import main as rqunit
from rqunit.schemas import installed_version, store_pack_version
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


def test_pack_pin_records_the_enforcing_version(tmp_path):
    _init(tmp_path)
    assert store_pack_version(tmp_path) == installed_version()


def test_unpinned_store_falls_back_to_the_installed_version(tmp_path):
    _init(tmp_path)
    (tmp_path / "spec" / "framework" / "pack.yaml").unlink()
    assert store_pack_version(tmp_path) == installed_version()


def test_rust_detection_writes_config_the_strict_reader_accepts(tmp_path):
    (tmp_path / "Cargo.toml").write_text("[package]\nname = \"app\"\n")
    result = _init(tmp_path)
    assert result.exit_code == 0 and "rust" in result.output
    loaded = config.load(tmp_path)
    assert loaded.rust.conformance_crate  # parsed, not defaulted past a bad file


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
    assert config.load(tmp_path).rust.trace_scan


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
