"""rqunit.toml consumer config. Invariants: a missing file means no stacks
(store-only operations need zero config; stack participation is always an
explicit declaration); any stack NAME is accepted — core carries no list of
supported languages; core interprets a closed key set per stack (`adapter`,
`literal_scan`) and passes everything else through untouched; malformed
shapes among the core-read keys are BadConfig errors, never silence."""

import shutil
from pathlib import Path

import pytest

from rqunit.config import Config, Role, Stack, load
from rqunit.errors import BadConfig
from rqunit.generate import targets
from rqunit.store import Store
from rqunit.trace import scan_tests

FIXTURES = Path(__file__).parent.parent / "fixtures"
# Core-owned: the seam under test is artifact-shaped observation, not Rust
# parsing — the adapter's kit tree is the adapter's to grow.
RUSTTREE = Path(__file__).parent.parent / "fixtures" / "scanned-tree"
REPO = Path(__file__).parent.parent


def _toml(tmp_path, body: str):
    (tmp_path / "rqunit.toml").write_text(body)
    return tmp_path


def test_missing_file_means_no_stacks(tmp_path):
    cfg = load(tmp_path)
    assert cfg == Config()
    assert cfg.stacks == () and cfg.stack("rust") is None


def test_any_stack_name_is_accepted_core_has_no_language_list(tmp_path):
    cfg = load(_toml(tmp_path, "[stacks.jvm]\n[stacks.rust]\n[stacks.cobol-85]\n"))
    assert [s.name for s in cfg.stacks] == ["cobol-85", "jvm", "rust"]
    assert cfg.stack("jvm") == Stack(name="jvm")


def test_core_keys_parse_and_the_rest_passes_through_opaquely(tmp_path):
    cfg = load(_toml(tmp_path, """
[stacks.rust]
literal_scan = ["**/tests"]
trace_scan = ["crates/*/Cargo.toml"]
conformance_crate = "tools/conformance"
service = "service-orders"

[[stacks.rust.routers]]
file = "http/src/routes/mod.rs"
function = "router"

[stacks.rust.adapter]
extractor = { artifact = "actual-surface.json" }
scanner = { cmd = ["adapters/rust/target/release/scan-checks", "--flag"] }
"""))
    stack = cfg.stack("rust")
    assert stack.literal_scan == ("**/tests",)
    assert stack.adapter.extractor == Role(artifact="actual-surface.json")
    assert stack.adapter.scanner == Role(cmd=("adapters/rust/target/release/scan-checks",
                                              "--flag"))
    assert stack.adapter.emitter is None            # undeclared = unavailable
    # Passthrough arrives verbatim — core never interprets or reshapes it.
    assert stack.options["trace_scan"] == ["crates/*/Cargo.toml"]
    assert stack.options["conformance_crate"] == "tools/conformance"
    assert stack.options["routers"] == [{"file": "http/src/routes/mod.rs",
                                         "function": "router"}]
    assert "adapter" not in stack.options and "literal_scan" not in stack.options


def test_a_role_is_cmd_xor_artifact(tmp_path):
    for body in (
        '[stacks.rust.adapter]\nextractor = { cmd = ["x"], artifact = "y" }\n',  # both
        "[stacks.rust.adapter]\nextractor = { }\n",                              # neither
    ):
        with pytest.raises(BadConfig) as caught:
            load(_toml(tmp_path, body))
        assert "exactly one of" in str(caught.value)


@pytest.mark.parametrize("content, expected", [
    ("[store]\nroot = 'elsewhere'\n", "unknown top-level"),      # store layout is fixed
    ("[stacks.Rust]\n", "must match"),                           # stack naming discipline
    ("[stacks.rust]\nliteral_scan = 'not-a-list'\n", "list of glob strings"),
    ("[stacks.rust.adapter]\nextracter = { artifact = 'x' }\n", "unknown"),  # typoed role
    ("[stacks.rust.adapter]\nextractor = { path = 'x' }\n", "unknown"),      # typoed key
    ("[stacks.rust.adapter]\nextractor = { cmd = [] }\n", "non-empty list"),
    ("[stacks.rust.adapter]\nextractor = { artifact = '' }\n", "non-empty"),
    ("[stacks.rust.adapter]\nextractor = 'a-string'\n", "must be a table"),
    ("not toml [", "not parseable"),
])
def test_malformed_core_read_shapes_are_errors_not_silence(tmp_path, content, expected):
    with pytest.raises(BadConfig) as caught:
        load(_toml(tmp_path, content))
    assert expected in str(caught.value)


def test_adapter_vocabulary_is_not_validated_here(tmp_path):
    """A typo in a passthrough key is the adapter manifest's problem
    (config_keys), not this loader's — core judging `routers` would be
    language knowledge."""
    cfg = load(_toml(tmp_path, "[stacks.rust]\ntrace_scam = ['x']\n"))
    assert cfg.stack("rust").options["trace_scam"] == ["x"]


def test_the_shipped_consumer_configs_load(tmp_path):
    """Every config this repo ships parses under the strict reader, and what
    a store declares round-trips. The property, not the census: exact values
    belong to the stores, and pinning them here breaks legitimate growth."""
    demo = load(REPO / "demo" / "order-management")
    assert demo.stack("rust").adapter.extractor.artifact   # extractor declared
    traced = load(FIXTURES / "store" / "traced")
    assert traced.stack("rust").options["trace_scan"]      # passthrough survives
    assert traced.stack("rust").adapter.extractor is None  # declares no roles


# ------------------------------------------------ scan and emit honor the file

def test_scan_tests_honors_declared_scanner_roles(tmp_path):
    root = tmp_path / "repo"
    shutil.copytree(RUSTTREE, root)
    assert scan_tests(root), "the fixture tree declares a scanner role"
    (root / "rqunit.toml").write_text("[stacks.rust]\n")     # role removed
    assert scan_tests(root) == []
    (root / "rqunit.toml").unlink()
    assert scan_tests(root) == []       # no declaration, no participation


def test_targets_hands_passthrough_options_to_the_emitter(tmp_path):
    """`conformance_crate` is emitter vocabulary now — core's whole part is
    delivering the passthrough table as request data. Where paths land is the
    adapter's decision, pinned by its own cargo tests."""
    from rqunit.generate import emit_request

    root = tmp_path / "repo"
    shutil.copytree(FIXTURES / "store" / "valid", root)
    (root / "rqunit.toml").write_text(
        '[stacks.rust]\nconformance_crate = "tools/conf"\n'
        '[stacks.rust.adapter]\nemitter = { artifact = "emit-response.json" }\n')
    request = emit_request(Store.load(root), load(root).stack("rust"))
    assert request["options"]["conformance_crate"] == "tools/conf"
