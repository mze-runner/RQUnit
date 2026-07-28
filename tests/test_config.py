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
