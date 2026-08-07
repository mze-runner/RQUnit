"""`rqunit adapter verify` — the compliance kit's own acceptance.

Invariants: a conforming kit passes; divergence from the committed
expectation, nondeterminism, and unrunnable roles are violations (exit 1)
with the fix named; a missing manifest or kit is a tool error (exit 2). The
real Rust adapter's run is covered by /check (it needs built binaries); here
a scripted fake adapter proves the verifier itself."""

import json
import sys
from pathlib import Path

from click.testing import CliRunner

from rqunit.cli.adapter import main as adapter_main

ARTIFACT = {"contract_version": 1, "generated_by": "fake-scanner 0.1",
            "checks": [{"id": "svc::orders::cancels", "path": "tests/orders.java",
                        "fn": "cancels", "verifies": ["RU-0001"]}]}

EMPTY = {"contract_version": 1, "generated_by": "fake-scanner 0.1", "checks": []}

CAT_SCANNER = f"""\
import json, sys, os
root = sys.argv[sys.argv.index("--root") + 1]
if os.path.exists(os.path.join(root, "rqunit.toml")):
    print(json.dumps({ARTIFACT!r}))
else:
    print(json.dumps({EMPTY!r}))
"""


def _adapter(tmp_path: Path, scanner_body: str = CAT_SCANNER) -> Path:
    root = tmp_path / "repo"
    home = root / "adapters" / "jvm"
    (home / "kit" / "scanner" / "tree").mkdir(parents=True)
    (home / "scanner.py").write_text(scanner_body)
    (home / "adapter.yaml").write_text(
        "contract_version: 1\n"
        "stack: jvm\n"
        "roles: [scanner]\n"
        "kit:\n"
        "  path: kit\n"
        "  commands:\n"
        f"    scanner: [\"{sys.executable}\", \"scanner.py\", ]\n".replace(", ]", "]"))
    (home / "kit" / "scanner" / "tree" / "rqunit.toml").write_text("[stacks.jvm]\n")
    (home / "kit" / "scanner" / "expected.json").write_text(json.dumps(ARTIFACT))
    return root


def _verify(root: Path):
    return CliRunner().invoke(adapter_main, ["verify", "--stack", "jvm",
                                             "--root", str(root)])


def test_a_conforming_kit_passes(tmp_path):
    result = _verify(_adapter(tmp_path))
    assert result.exit_code == 0, result.output
    assert "0 problem(s)" in result.output


def test_divergence_from_the_expectation_names_the_fix(tmp_path):
    root = _adapter(tmp_path)
    drifted = dict(ARTIFACT, checks=[])
    (root / "adapters" / "jvm" / "scanner.py").write_text(
        f"print('{json.dumps(drifted)}')")
    result = _verify(root)
    assert result.exit_code == 1
    assert "diverges" in result.output and "regenerate" in result.output


def test_nondeterminism_is_a_violation(tmp_path):
    root = _adapter(tmp_path, scanner_body=(
        "import json, os\n"
        "print(json.dumps({'contract_version': 1,\n"
        "                  'generated_by': 'fake ' + os.urandom(4).hex(),\n"
        "                  'checks': []}))\n"))
    result = _verify(root)
    assert result.exit_code == 1
    assert "byte-deterministic" in result.output


def test_a_role_the_kit_cannot_run_is_unverified_not_skipped(tmp_path):
    root = _adapter(tmp_path)
    manifest = root / "adapters" / "jvm" / "adapter.yaml"
    manifest.write_text(manifest.read_text().replace(
        "roles: [scanner]", "roles: [scanner, emitter]"))
    result = _verify(root)
    assert result.exit_code == 1
    assert "emitter" in result.output and "unverified" in result.output


def test_a_missing_manifest_is_a_tool_error(tmp_path):
    (tmp_path / "repo").mkdir()
    result = _verify(tmp_path / "repo")
    assert result.exit_code == 2
    assert "manifest" in result.output


def test_an_empty_tree_probe_guards_the_zero_checks_contract(tmp_path):
    """A scanner that errors on a tree declaring nothing violates the
    'nothing participates is an observation' rule."""
    root = _adapter(tmp_path, scanner_body=(
        "import json, sys, os\n"
        "root = sys.argv[sys.argv.index('--root') + 1]\n"
        "if not os.path.exists(os.path.join(root, 'rqunit.toml')):\n"
        "    sys.exit(1)\n"                      # wrong: absence is not an error
        f"print(json.dumps({ARTIFACT!r}))\n"))
    result = _verify(root)
    assert result.exit_code == 1
    assert "observation, not an error" in result.output


def test_the_probe_judges_structure_not_serialized_text(tmp_path):
    """A compliant scanner may format its JSON however it likes — compact
    zero-checks output must pass the empty-tree probe."""
    root = _adapter(tmp_path, scanner_body=(
        "import json, sys, os\n"
        "root = sys.argv[sys.argv.index('--root') + 1]\n"
        "if os.path.exists(os.path.join(root, 'rqunit.toml')):\n"
        f"    print(json.dumps({ARTIFACT!r}))\n"
        "else:\n"
        f"    print(json.dumps({EMPTY!r}, separators=(',', ':')))\n"))
    result = _verify(root)
    assert result.exit_code == 0, result.output
