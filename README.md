# RQUnit

Requirements that can be verified, stored beside the code they govern.

RQUnit manages requirements as small, individually addressable units that live in
your repository, travel on your branches, and carry machine-checkable links to the
tests, contracts, and models that prove them. It is built for codebases where agents
do much of the writing, and it starts from two refusals:

> A requirement that cannot be mechanically verified is a preference.
> A specification that can drift from its code silently is decoration.

So enforcement is not advice. Lints, consistency checks, and conformance gates block
commits; requirement status is *computed* from evidence rather than asserted by
whoever last touched a ticket.

## What it gives you

- **Atomic requirements.** One requirement, one file, one normative sentence in a
  constrained grammar. No paragraphs hiding three obligations.
- **Facts declared once.** Endpoints, message subjects, limits, and vocabularies live
  in a manifest and are *referenced* from requirements — so changing a fact changes
  it everywhere, and a requirement can never quietly contradict the interface.
- **Verification that is real.** Every requirement names how it is proven. Missing
  proof is recorded honestly as debt rather than assumed.
- **Drift caught mechanically.** The framework reconciles your manifests against what
  the code actually exposes, and generates model-conformance suites from statecharts
  rather than trusting a diagram nobody re-reads.
- **Two human gates, kept apart.** One asks "is this what I said?" at authoring time;
  the other asks "does the built thing achieve the intent?" after delivery. Both are
  recorded; neither is inferrable from the other.
- **Context for agents that is complete by construction.** A task packet carries the
  exact, immutable context for one task; a question it cannot answer is a
  specification defect, not licence to guess.

## Install

```bash
uv tool install rqunit      # or: uv sync, for development in this repo
rqunit --help
```

## Quickstart

```bash
cd your-project
rqunit init                 # scaffold a store, detect the stack, write rqunit.toml
# capture intent, compile requirements, then:
rqunit lint                 # per-artifact rules
rqunit check                # cross-artifact consistency
rqunit doctor               # structural health (advisory)
rqunit report               # a snapshot for a review audience
```

Exit codes everywhere: `0` pass, `1` violations, `2` tool error.

## Language support

The framework is language-neutral by construction: every *judgment* lives in the
core, and everything language-specific lives in a small adapter behind three pinned
JSON contracts — an extractor (what the code exposes), an emitter (rendering the
framework's test plan as idiomatic tests), and a scanner (finding tests and their
traceability annotations). Supporting a language costs an adapter, never a second
copy of the rules.

Adapters live under [`adapters/`](adapters).

## Documentation

| Document | For |
|---|---|
| [HANDBOOK.md](HANDBOOK.md) | daily use: recipes, the CLI, and the full rule catalogue |
| [docs/ru-framework-spec.md](docs/ru-framework-spec.md) | the normative specification |
| [docs/formats.md](docs/formats.md) | every pinned format and grammar |

Where they disagree, the specification wins.
