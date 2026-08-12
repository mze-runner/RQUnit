"""The `rqunit` umbrella CLI: every lifecycle verb is mounted and delegates to
the same implementation the spec-* aliases use."""

import json
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


def test_lint_reports_an_unwritable_projection_as_a_tool_error(tmp_path):
    """`lint` owns one projection and refreshes it in place, so it is the one
    command in the product that writes while promising to read. Unguarded that
    ended a read-only checkout — an ordinary CI shape — with a traceback, which
    is none of the three exits the CLI contract states."""
    import shutil
    from rqunit.cli.lint import main as lint_main

    root = tmp_path / "store"
    shutil.copytree(Path(__file__).parent.parent / "fixtures" / "store" / "valid", root)
    queue = root / "spec" / "projections" / "suspect-queue.json"
    queue.unlink(missing_ok=True)
    queue.parent.chmod(0o500)
    try:
        result = CliRunner().invoke(lint_main, ["--store", str(root), "--format", "text"])
    finally:
        queue.parent.chmod(0o700)

    assert result.exit_code == 2, result.output
    assert "tool error" in result.output
    assert "suspect-queue.json" in result.output
    assert "writable" in result.output          # names what to do about it
    assert not isinstance(result.exception, PermissionError)


def test_lint_announces_a_projection_it_refreshed_and_stays_quiet_otherwise(tmp_path):
    """A command that writes says so — but only when it wrote. The write is
    conditional on the content changing, which is what keeps a lint run out of
    `git status` and is why announcing unconditionally would be noise."""
    import shutil
    from rqunit.cli.lint import main as lint_main

    root = tmp_path / "store"
    shutil.copytree(Path(__file__).parent.parent / "fixtures" / "store" / "valid", root)
    (root / "spec" / "projections" / "suspect-queue.json").unlink(missing_ok=True)

    runner = CliRunner()
    first = runner.invoke(lint_main, ["--store", str(root), "--format", "text"])
    second = runner.invoke(lint_main, ["--store", str(root), "--format", "text"])

    assert "refreshed" in first.output
    assert "suspect-queue.json" in first.output
    assert "refreshed" not in second.output, "an unchanged queue is written and said nothing"


def test_the_json_report_stays_parseable_while_a_projection_is_announced(tmp_path):
    """The announcement goes to stderr for this reason: stdout is the report, and
    a consumer piping `--format json` into a parser must not receive prose."""
    import shutil
    from rqunit.cli.lint import main as lint_main

    root = tmp_path / "store"
    shutil.copytree(Path(__file__).parent.parent / "fixtures" / "store" / "valid", root)
    (root / "spec" / "projections" / "suspect-queue.json").unlink(missing_ok=True)

    result = CliRunner().invoke(lint_main, ["--store", str(root)])

    json.loads(result.stdout)                    # raises if the line leaked into stdout
    assert "refreshed" in result.stderr


def test_a_refused_table_is_named_rather_than_echoed(tmp_path):
    """`artifacts` on a service manifest is refused because C5 resolves the
    reference against the shared table only, so a local one is unreferenceable.
    A boolean subschema would report "False schema does not allow {…}" with the
    whole table echoed and nothing named — Hard Rule 6's failure mode — so the
    refusal is spelled as a `not: required` the report can state."""
    from rqunit.cli.lint import main as lint_main

    root = _broken_store(
        tmp_path,
        'service: service-orders\nversion: "1.0"\nendpoints:\n'
        '  - {id: get_order, method: GET, path: /x, access: public, ru: FEAT-x}\n'
        'artifacts:\n  jwt-access-token:\n'
        '    fields: [{name: sub, presence: always}]\n')
    result = CliRunner().invoke(lint_main, ["--store", str(root), "--format", "text"])

    assert "`artifacts`" in result.output
    assert "does not carry" in result.output
    assert "False schema" not in result.output
    assert "jwt-access-token" not in result.output, "the table must not be echoed back"


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
