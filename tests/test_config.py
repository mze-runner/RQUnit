"""rqunit.toml consumer config (product Phase I). Invariants: missing file =
generic conventional defaults (store-only operations need zero config);
values override; unknown tables/keys/shapes are BadConfig errors — a typo
silently ignored would read as configured; scan and emit sites actually
honor the file."""

import shutil
from pathlib import Path

import pytest

from rqunit.config import Config, load
from rqunit.errors import BadConfig
from rqunit.generate import targets
from rqunit.store import Store
from rqunit.trace import scan_tests

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_missing_file_yields_generic_defaults(tmp_path):
    cfg = load(tmp_path)
    assert cfg == Config()
    assert cfg.rust.trace_scan == ("**/Cargo.toml",)
    assert cfg.rust.conformance_crate == "spec-conformance-tests"


def test_values_override_defaults(tmp_path):
    (tmp_path / "rqunit.toml").write_text(
        '[stacks.rust]\ntrace_scan = ["crates/*/Cargo.toml"]\n'
        'conformance_crate = "tools/conformance"\n')
    cfg = load(tmp_path)
    assert cfg.rust.trace_scan == ("crates/*/Cargo.toml",)
    assert cfg.rust.conformance_crate == "tools/conformance"
    assert cfg.rust.trace_diff == ("*/tests/*.rs",)   # untouched keys keep defaults


@pytest.mark.parametrize("content", [
    "[stacks.rust]\ntrace_scam = []\n",              # typoed key
    "[stacks.java]\n",                               # unsupported stack
    "[store]\nroot = 'elsewhere'\n",                 # store layout is not configurable
    "[stacks.rust]\ntrace_scan = 'not-a-list'\n",
    "[stacks.rust]\nconformance_crate = 3\n",
    "not toml [",
])
def test_unknown_or_malformed_config_is_an_error(tmp_path, content):
    (tmp_path / "rqunit.toml").write_text(content)
    with pytest.raises(BadConfig):
        load(tmp_path)


def test_scan_tests_honors_trace_scan(tmp_path):
    root = tmp_path / "repo"
    shutil.copytree(FIXTURES / "rusttree", root)
    assert scan_tests(root)                                    # default finds service-x
    (root / "rqunit.toml").write_text('[stacks.rust]\ntrace_scan = ["nothing/Cargo.toml"]\n')
    assert scan_tests(root) == []


def test_targets_honors_conformance_crate(tmp_path):
    root = tmp_path / "repo"
    shutil.copytree(FIXTURES / "store" / "valid", root)
    (root / "rqunit.toml").write_text('[stacks.rust]\nconformance_crate = "tools/conf"\n')
    out = targets(Store.load(root), root)
    suite_paths = [p for p in out if p.suffix == ".rs" and "tests" in p.parts]
    assert suite_paths and all(str(p).startswith(str(root / "tools" / "conf")) for p in suite_paths)
    trace_map = out[root / "spec" / "projections" / "trace-map.json"]
    assert '"conf::' in trace_map                              # basename = package prefix
    assert "spec-conformance-tests" not in trace_map


# ------------------------------------------------ composition is configuration

def _toml(tmp_path, body: str):
    (tmp_path / "rqunit.toml").write_text(body)
    return tmp_path


def test_router_composition_round_trips(tmp_path):
    """Which router mounts where is a fact about one repository, so it belongs
    here rather than as a constant in adapter source."""
    cfg = load(_toml(tmp_path, """
[stacks.rust]
service = "service-orders"

[[stacks.rust.routers]]
file = "http/src/routes/mod.rs"
function = "router"

[[stacks.rust.routers]]
file = "http/src/routes/orders/mod.rs"
function = "router"
prefix = "/api/v1/orders"
access = "protected"

[stacks.rust.messages]
subject_sources = ["wire-contracts/src"]
publisher_sources = ["adapters/nats/src"]
"""))
    assert cfg.rust.service == "service-orders"
    assert [r.function for r in cfg.rust.routers] == ["router", "router"]
    assert cfg.rust.routers[1].prefix == "/api/v1/orders"
    assert cfg.rust.routers[0].prefix == ""            # optional, defaults empty
    assert cfg.rust.messages.subject_sources == ("wire-contracts/src",)


def test_a_router_that_cannot_be_named_is_an_error(tmp_path):
    with pytest.raises(BadConfig) as caught:
        load(_toml(tmp_path, """
[stacks.rust]
[[stacks.rust.routers]]
file = "http/src/routes/mod.rs"
"""))
    assert "cannot find a router it cannot name" in str(caught.value)


def test_typos_in_the_new_tables_are_errors_not_silence(tmp_path):
    for body, expected in (
        ("[stacks.rust]\n[[stacks.rust.routers]]\nfile='a'\nfunction='r'\ntier='x'\n",
         "unknown router key"),
        ("[stacks.rust]\n[stacks.rust.messages]\nsubjects=['a']\n", "unknown messages key"),
    ):
        with pytest.raises(BadConfig) as caught:
            load(_toml(tmp_path, body))
        assert expected in str(caught.value)


def test_defaults_survive_for_a_repo_that_configures_nothing(tmp_path):
    cfg = load(tmp_path)
    assert cfg.rust.routers == () and cfg.rust.service == ""
