"""TASK-060/061 acceptance: in-bound passes, must_not_touch blocked with the
correct RU cited, outside-both passes (H1 blocks negative scope ONLY); H2
audits out-of-owns writes and NEVER blocks; both inert without a packet."""

import json
from pathlib import Path

from click.testing import CliRunner

from rqunit.cli.hooks import main as hooks_cli
from rqunit.hooks import h1_verdict, h2_record, path_matches

FIXTURES = Path(__file__).parent.parent / "fixtures"
HOOKS = FIXTURES / "store" / "hooks"


# ------------------------------------------------------------ glob semantics

def test_bare_globs_are_containment_prefixes():
    assert path_matches("service-billing/http/src/lib.rs", "service-billing")
    assert not path_matches("service-billing-extras/lib.rs", "service-billing")


def test_wildcard_globs_use_fnmatch():
    assert path_matches("service-orders/adapters/postgres/secrets/key.pem",
                        "service-orders/adapters/*/secrets")
    assert not path_matches("service-orders/adapters/postgres/config.rs",
                            "service-orders/adapters/*/secrets")


# ------------------------------------------------------------ H1

def test_h1_blocks_must_not_touch_and_cites_the_ru():
    blocked, message = h1_verdict(HOOKS, "service-billing/http/src/routes/mod.rs")
    assert blocked and "RU-0142" in message and "TASK-0007" in message


def test_h1_allows_in_owns_paths():
    assert h1_verdict(HOOKS, "service-orders/domain/src/lib.rs") == (False, None)


def test_h1_allows_paths_outside_both_scopes():
    # H1 blocks NEGATIVE scope only — outside-owns is H2's audit, never a block.
    assert h1_verdict(HOOKS, "storefront-web/src/main.rs") == (False, None)


def test_h1_inert_without_active_packet(tmp_path):
    assert h1_verdict(tmp_path, "service-billing/anything.rs") == (False, None)


def test_h1_handles_absolute_paths_and_never_resolves_relative_against_cwd():
    # Regression: a relative payload once resolved against the CLI's cwd
    # (spec-tools/), mangling it to spec-tools/service-billing/... and missing
    # the block. Relative = repo-root-relative AS-IS; absolute = relativized.
    blocked_abs, _ = h1_verdict(HOOKS, str(HOOKS / "service-billing" / "x.rs"))
    blocked_rel, _ = h1_verdict(HOOKS, "service-billing/x.rs")
    assert blocked_abs and blocked_rel


def test_h1_cli_exit_codes():
    ok = CliRunner().invoke(hooks_cli, ["h1", "--store", str(HOOKS),
                                        "--path", "service-orders/domain/src/lib.rs"])
    assert ok.exit_code == 0
    blocked = CliRunner().invoke(hooks_cli, ["h1", "--store", str(HOOKS),
                                             "--path", "service-billing/http/src/lib.rs"])
    assert blocked.exit_code == 1 and "RU-0142" in blocked.output


# ------------------------------------------------------------ H2

def test_h2_audits_out_of_owns_with_task_path_and_globs(tmp_path):
    import shutil
    root = tmp_path / "store"
    shutil.copytree(HOOKS, root)
    record = h2_record(root, "storefront-web/src/main.rs")
    assert record["task"] == "TASK-0007"
    assert record["path"] == "storefront-web/src/main.rs"
    assert record["owns"] and record["matched"] is False
    result = CliRunner().invoke(hooks_cli, ["h2", "--store", str(root),
                                            "--path", "storefront-web/src/main.rs"])
    assert result.exit_code == 0                                   # H2 NEVER blocks
    log = root / "spec" / "projections" / "scope-audit.jsonl"
    entry = json.loads(log.read_text().splitlines()[-1])
    assert entry["path"] == "storefront-web/src/main.rs"


def test_h2_silent_for_in_owns_writes():
    assert h2_record(HOOKS, "service-orders/application/src/lib.rs") is None


def test_h2_inert_without_active_packet(tmp_path):
    assert h2_record(tmp_path, "anything.rs") is None
