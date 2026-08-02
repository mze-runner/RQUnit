"""The `rqunit` umbrella CLI: every lifecycle verb is mounted and delegates to
the same implementation the spec-* aliases use."""

from pathlib import Path

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
