"""The `rqunit` umbrella CLI: every lifecycle verb is mounted and delegates to
the same implementation the spec-* aliases use."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from rqunit.cli.rqunit import main as rqunit

FIXTURES = Path(__file__).parent.parent / "fixtures"

VERBS = ["init", "lint", "check", "trace", "activate", "review", "impact",
         "assemble", "generate", "index", "hooks"]


def test_every_lifecycle_verb_is_mounted():
    result = CliRunner().invoke(rqunit, ["--help"])
    assert result.exit_code == 0
    for verb in VERBS:
        assert f"\n  {verb}" in result.output or f" {verb} " in result.output, verb


def test_grouped_verbs_expose_their_subcommands():
    for verb, subs in (("activate", ["batch", "restamp"]),
                       ("review", ["record", "guard"]),
                       ("assemble", ["build", "disarm"]),
                       ("generate", ["all", "check", "scan-literals"]),
                       ("hooks", ["h1", "h2"])):
        result = CliRunner().invoke(rqunit, [verb, "--help"])
        assert result.exit_code == 0
        for sub in subs:
            assert sub in result.output, f"{verb} {sub}"


def test_ruf_lint_delegates_end_to_end():
    ok = CliRunner().invoke(rqunit, ["lint", "--store", str(FIXTURES / "store" / "valid"),
                                  "--format", "text"])
    assert ok.exit_code == 0
    red = CliRunner().invoke(rqunit, ["lint", "--store", str(FIXTURES / "lints" / "L01" / "fail"),
                                   "--only", "L1", "--format", "text"])
    assert red.exit_code == 1 and "L1" in red.output


# ------------------------------------------------- schema-stage reporting
# Nothing exercised this branch: the suite stayed green through a NameError
# that broke `rqunit lint` on every unloadable store. A store that will not
# load is the first thing a new consumer meets, so it is worth its own tests.

def _broken_store(tmp_path, manifest_body: str) -> Path:
    import shutil
    root = tmp_path / "store"
    shutil.copytree(Path(__file__).parent.parent / "fixtures" / "store" / "valid", root)
    (root / "spec" / "manifests" / "service-orders.manifest.yaml").write_text(manifest_body)
    return root


@pytest.mark.parametrize("verb", ["lint", "check"])
def test_an_unloadable_store_is_reported_not_crashed(tmp_path, verb):
    """A store that cannot load is a finding, not a tool error — exit 1, not 2,
    and certainly not a traceback."""
    from rqunit.cli.check import main as check_main
    from rqunit.cli.lint import main as lint_main

    root = _broken_store(tmp_path, 'service: service-orders\nversion: "1.0"\n')
    cli = {"lint": lint_main, "check": check_main}[verb]
    result = CliRunner().invoke(cli, ["--store", str(root), "--format", "text"])
    assert result.exit_code == 1, result.output
    assert "SCHEMA" in result.output


@pytest.mark.parametrize("verb", ["lint", "check"])
def test_the_schema_report_locates_the_problem_and_teaches(tmp_path, verb):
    """Both verbs render this, and they used to render it differently. The
    message must name the rule rather than echo the document, the path must be
    store-relative and appear once, and a suggestion is mandatory."""
    from rqunit.cli.check import main as check_main
    from rqunit.cli.lint import main as lint_main

    root = _broken_store(tmp_path, 'service: service-orders\nversion: "1.0"\n')
    cli = {"lint": lint_main, "check": check_main}[verb]
    result = CliRunner().invoke(cli, ["--store", str(root), "--format", "text"])

    assert "at least one is required" in result.output
    assert "endpoints" in result.output and "messages" in result.output
    assert "suggestion:" in result.output
    assert str(root) not in result.output, "absolute paths differ per machine"
    assert "is not valid under any of the given schemas" not in result.output


def test_a_leaf_failure_names_its_key_and_not_the_whole_document(tmp_path):
    """The defect this replaced: jsonschema reports a composite failure at the
    composite, echoing every key back and naming none of them."""
    from rqunit.cli.lint import main as lint_main

    root = _broken_store(
        tmp_path,
        'service: service-orders\nversion: "1.0"\nendpoints:\n'
        '  - {id: "Bad-ID", method: GET, path: /x, access: public, ru: FEAT-x}\n')
    result = CliRunner().invoke(lint_main, ["--store", str(root), "--format", "text"])
    assert "endpoints[0].id" in result.output
    assert "service-orders" not in result.output.split("suggestion:")[0].split("id")[-1]
