"""Scanner seam — where per-language test discovery plugs in, now out of
process behind the scanned-checks contract.

Invariants: core delegates discovery to declared scanner roles and never
scans on its own; only declared stacks run; a second stack merges without a
core change; L14 newness is base-vs-head set difference over the scanners'
own observations (a detached worktree for cmd mode, `git show` for artifact
mode) — and the worktree never leaks."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from rqunit import trace
from rqunit.config import Config, Role, Stack
from rqunit.trace import l14_gate, scan_tests

FIXTURES = Path(__file__).parent.parent / "fixtures"
RUSTTREE = FIXTURES / "rusttree"

# A stand-in scanner obeying the stdio contract: its observation for a tree
# is whatever scanned-checks.json that tree carries. Reading the --root
# argument (not cwd) is the property the worktree base scan depends on.
CAT_SCANNER = """\
import sys
root = sys.argv[sys.argv.index("--root") + 1]
sys.stdout.write(open(root + "/scanned-checks.json").read())
"""


def _artifact(*checks) -> str:
    return json.dumps({
        "contract_version": 1,
        "generated_by": "fake-scanner 0.1",
        "checks": [
            {"id": f"svc::{file}::{fn}", "path": f"tests/{file}.java", "fn": fn,
             "verifies": verifies}
            for file, fn, verifies in checks
        ],
    })


def test_scanning_goes_through_declared_roles_only(tmp_path, monkeypatch):
    """Core delegates; it never scans a tree on its own. A registered-looking
    stack with no scanner role contributes nothing and is reported as
    unscanned rather than silently skipped."""
    root = tmp_path / "repo"
    shutil.copytree(RUSTTREE, root)
    assert scan_tests(root), "baseline: the declared artifact-mode scanner observes"

    (root / "rqunit.toml").write_text("[stacks.rust]\n")     # role removed
    assert scan_tests(root) == []
    assert trace.unscanned_stacks(root) == ["rust"]


def test_a_second_stack_merges_without_core_changes(tmp_path):
    root = tmp_path / "repo"
    shutil.copytree(RUSTTREE, root)
    before = {c.id for c in scan_tests(root)}

    (root / "jvm-checks.json").write_text(
        _artifact(("PaymentTest", "refunds", ["RU-0001"])))
    toml = root / "rqunit.toml"
    toml.write_text(toml.read_text()
                    + '\n[stacks.jvm.adapter]\nscanner = { artifact = "jvm-checks.json" }\n')

    merged = {c.id for c in scan_tests(root)}
    assert merged == before | {"svc::PaymentTest::refunds"}   # union, no collision


def test_cmd_mode_scanner_receives_the_root_it_must_observe(tmp_path):
    root = tmp_path / "repo"
    shutil.copytree(RUSTTREE, root)
    script = tmp_path / "scanner.py"
    script.write_text(CAT_SCANNER)
    (root / "rqunit.toml").write_text(
        "[stacks.rust.adapter]\n"
        f'scanner = {{ cmd = ["{sys.executable}", "{script}"] }}\n')
    ids = {c.id for c in scan_tests(root)}
    assert "service-x-application::sample_tests::traced_single" in ids


# ------------------------------------------------------------ L14 set difference

def _repo(tmp_path, config: str) -> Path:
    root = tmp_path / "repo"
    shutil.copytree(RUSTTREE, root)
    (root / "rqunit.toml").write_text(config)
    run = lambda *a: subprocess.run(["git", "-C", str(root), *a],
                                    check=True, capture_output=True)
    run("init", "-q")
    run("-c", "user.email=t@t", "-c", "user.name=t", "add", "-A")
    run("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
    return root


def _add_untraced(root: Path, fn: str):
    path = root / "scanned-checks.json"
    data = json.loads(path.read_text())
    data["checks"].append({
        "id": f"service-x-application::sample_tests::{fn}",
        "path": "service-x/tests/sample_tests.rs", "fn": fn, "verifies": []})
    path.write_text(json.dumps(data))


def test_setdiff_via_worktree_scans_base_and_head_with_the_same_scanner(tmp_path):
    """Cmd mode: the base observation comes from a detached checkout handed to
    the SAME declared scanner via --root — the head's dirty working tree and
    the base commit are two trees, one contract."""
    script = tmp_path / "scanner.py"
    script.write_text(CAT_SCANNER)
    root = _repo(tmp_path, "[stacks.rust.adapter]\n"
                           f'scanner = {{ cmd = ["{sys.executable}", "{script}"] }}\n')

    assert l14_gate(None, root, "HEAD") == []           # no drift, no findings
    _add_untraced(root, "fresh_and_untraced")           # dirty tree, uncommitted
    violations = l14_gate(None, root, "HEAD")
    assert len(violations) == 1 and "fresh_and_untraced" in violations[0]


def test_setdiff_leaves_no_worktree_behind(tmp_path):
    script = tmp_path / "scanner.py"
    script.write_text(CAT_SCANNER)
    root = _repo(tmp_path, "[stacks.rust.adapter]\n"
                           f'scanner = {{ cmd = ["{sys.executable}", "{script}"] }}\n')
    l14_gate(None, root, "HEAD")
    listing = subprocess.run(["git", "-C", str(root), "worktree", "list"],
                             capture_output=True, text=True).stdout
    assert len(listing.strip().splitlines()) == 1       # only the main tree


def test_setdiff_cleans_up_even_when_the_scanner_fails(tmp_path):
    script = tmp_path / "scanner.py"
    script.write_text("import sys; sys.exit(1)")
    root = _repo(tmp_path, "[stacks.rust.adapter]\n"
                           f'scanner = {{ cmd = ["{sys.executable}", "{script}"] }}\n')
    # Head scan already fails — point head at the committed artifact so only
    # the base scan exercises the failing command.
    with pytest.raises(Exception):
        trace._worktree_ids(root, "HEAD", trace._scanner_stacks(root)[0])
    listing = subprocess.run(["git", "-C", str(root), "worktree", "list"],
                             capture_output=True, text=True).stdout
    assert len(listing.strip().splitlines()) == 1


def test_setdiff_artifact_mode_reads_the_base_artifact_from_git(tmp_path):
    """Artifact mode needs no checkout: base = git show REF:path. A base ref
    where the artifact did not exist yet means base observed nothing — every
    current check is new."""
    config = ('[stacks.rust.adapter]\n'
              'scanner = { artifact = "scanned-checks.json" }\n')
    root = _repo(tmp_path, config)
    assert l14_gate(None, root, "HEAD") == []
    _add_untraced(root, "fresh_and_untraced")
    violations = l14_gate(None, root, "HEAD")
    assert len(violations) == 1 and "fresh_and_untraced" in violations[0]


def test_setdiff_resolves_store_paths_below_the_repo_top_level(tmp_path):
    """'Requirements stored beside the code they govern' makes a nested store
    the normal case: bare REF:path resolves from the repo top level, so both
    transports must follow the repo prefix — or the base observation reads
    the wrong tree and the whole burn-down turns into a hard block."""
    repo = tmp_path / "repo"
    repo.mkdir()
    store = repo / "sub" / "store"
    shutil.copytree(RUSTTREE, store)
    script = tmp_path / "scanner.py"
    script.write_text(CAT_SCANNER)
    run = lambda *a: subprocess.run(["git", "-C", str(repo), *a],
                                    check=True, capture_output=True)
    run("init", "-q")
    run("-c", "user.email=t@t", "-c", "user.name=t", "add", "-A")
    run("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")

    # artifact mode: git-show path resolution follows the store prefix
    assert l14_gate(None, store, "HEAD") == []
    # cmd mode: the worktree target is the store's subtree, not the repo root
    (store / "rqunit.toml").write_text(
        "[stacks.rust.adapter]\n"
        f'scanner = {{ cmd = ["{sys.executable}", "{script}"] }}\n')
    assert l14_gate(None, store, "HEAD") == []
    _add_untraced(store, "fresh_and_untraced")
    violations = l14_gate(None, store, "HEAD")
    assert len(violations) == 1 and "fresh_and_untraced" in violations[0]


def test_l14_with_nothing_to_observe_is_a_tool_error_not_a_pass(tmp_path):
    """Deleting the scanner declaration must not become a one-line L14
    bypass: a gate that observes nothing cannot pass."""
    root = _repo(tmp_path, "[stacks.rust]\n")
    with pytest.raises(RuntimeError) as caught:
        l14_gate(None, root, "HEAD")
    assert "scanner" in str(caught.value)


def test_setdiff_artifact_absent_at_base_means_base_observed_nothing(tmp_path):
    config = ('[stacks.rust.adapter]\n'
              'scanner = { artifact = "scanned-checks.json" }\n')
    root = _repo(tmp_path, config)
    subprocess.run(["git", "-C", str(root), "rm", "-q", "--cached", "scanned-checks.json"],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "drop artifact"], check=True, capture_output=True)
    violations = l14_gate(None, root, "HEAD")
    # every untraced check in the head observation is new against an empty base
    assert violations and all("L14" in v for v in violations)
