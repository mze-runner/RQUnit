---
name: framework-revision
description: How to change the framework itself — the specification, the formats reference, a JSON schema, the reference-token grammar, or the canonical hash. These are schema-revision events with consumer-visible consequences, not edits. Load before modifying anything under docs/ or src/rqunit/pack/schemas/.
---

# Revising the framework

The specification and the formats reference are normative for every consumer.
Changing them is a **revision event**: versioned, propagated in one change, and
justified. Nothing here is a casual edit.

## The blast radius, worst first

**The canonical hash is the most dangerous thing in this codebase.** Gate
stamps and link fingerprints are hashes over a canonical serialization. Change
its bytes — key order, separators, unicode handling, which fields are included
— and **every stamp in every consumer store becomes invalid simultaneously**.
There is no migration that repairs it without a re-stamp under a human
reviewer, which is exactly the review the stamp exists to record.

Treat the canonicalizer as frozen. If it must change, that is a major version,
announced, with a documented re-stamp procedure — never a quiet fix.

**Next: schema tightening.** A schema that admits less than it did yesterday
invalidates stores that were legal yesterday. Tightening is legitimate — that
is how defect classes get closed — but it must be announced in the version
line, and the error message must tell an affected consumer what to do.

**Then: rule severity.** Promoting `warning` to `error` turns someone's
tolerated burn-down into a red build. Do it when the debt is genuinely
finished, not when it looks tidy.

## Invariants that must hold across a revision

- **Schema and grammar agree.** A shape a schema admits but the token grammar
  cannot reference is a defect — a consumer can declare a fact and then find no
  way to cite it. A meta-test guards this; extend both together, always.
- **The EARS golden suite is the parser's contract.** Extend the suite before
  the grammar, never after. A grammar change that only shows up as "the tests
  still pass" has no evidence behind it.
- **Fixtures move with the schema.** Every schema has pass and fail fixtures;
  a tightening that leaves fixtures untouched has not been tested.

## The sequence

1. State the change and its consequence in the specification's status line —
   what changed, and what a consumer must do if anything.
2. Update the schema, the grammar, and the affected rule together.
3. Update fixtures — including a regression fixture for the case that motivated
   the change.
4. Update `HANDBOOK.md`: rule catalogue, and any recipe whose steps changed.
5. Bump the pack version in `pyproject.toml`.
6. Run the full suite plus the CLI against the fixture stores.

## Writing the documents

The specification is normative and terse; the formats reference pins exact
shapes; the handbook explains and gives recipes. Where they disagree the
specification wins, and the handbook says so about itself.

All three are **timeless**. No status, no counts, no dates, no roadmap
position, no narrative about how a decision was reached. A reader six months
from now must not be able to tell which release wrote a paragraph. Dated design
papers under `docs/` are the exception and must announce their date in the
first lines.

Examples use a generic order-management domain. No consumer's service names,
vocabulary, or paths — ever, including in error messages and fixtures.

## What not to do

Do not add an extension point "for later". Contract kinds are a closed set, the
model dialect is flat, and there is no generic assertion DSL — each of those is
a deliberate refusal, and each gets re-proposed roughly once a quarter. Extend
by revision when a real case arrives, and let the case justify the shape.
