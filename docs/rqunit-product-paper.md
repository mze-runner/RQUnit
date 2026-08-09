# RQUnit — Orientation

For whoever works **on** RQUnit, human or agent. It covers what the product is,
how it is built, and which decisions are settled and why — enough to make a
change without re-deriving the architecture or re-opening questions that are
closed.

If you want to *use* RQUnit rather than change it, read [the
handbook](../HANDBOOK.md). The normative documents are [the
specification](ru-framework-spec.md) and [the formats
reference](formats.md); where anything here disagrees with them, they win.

---

## 1. What RQUnit is

A requirements framework for software built with heavy agent participation. It
starts from two refusals:

> A requirement that cannot be mechanically verified is a preference.
> A specification that can drift from its code silently is decoration.

Requirements are small, individually addressable units stored beside the code
they govern, in the same version control, carrying machine-checkable links to
the artifacts that prove them. Enforcement is not advice: it is lints,
consistency checks, runtime hooks, and gates that block commits.

**The problem it solves.** Conventional requirements tooling is database-backed
and therefore lives *beside* the code — which is precisely why it drifts. A
requirement in a separate system cannot be branched with the change that alters
it, reviewed in the pull request that implements it, or proven by the test that
verifies it. RQUnit puts the requirement in the repository and makes the proof a
link the tool can follow.

**Why now.** When agents write most of the code, the binding constraint moves
from typing to *specifying*. An agent will implement whatever it is told,
including the wrong thing, confidently. The scarce resource becomes an
unambiguous, complete, verifiable statement of intent — and the ability to prove
mechanically that what was built matches it.

## 2. The model

### Artifacts

| Artifact | Id | Mutability | Holds |
|---|---|---|---|
| **INT** | `INT-<ULID>` | immutable | captured human intent, verbatim |
| **RU** | `RU-[SEG-]<seq>` | append-only, superseded never edited | one normative behaviour statement |
| **FEAT** | `FEAT-<slug>` | freely | grouping and one goal sentence; never normative |
| **Manifest** | service slug | Gate-1-gated | interface facts: endpoints, messages, values, audit events |
| **MDL** | `MDL-<slug>` | Gate-1-gated | a statechart; conformance suites are generated from it |
| **GAP** | `GAP-<ULID>` | resolved, not edited | an ambiguity blocking or deferring activation |
| **ADR** | `ADR-<slug>` | editable prose | the reasoning behind requirements |

### The knowledge classes, kept apart

The single most load-bearing division in the model:

- **Intent** — what a human said. Verbatim, immutable, never paraphrased.
- **Behaviour** — one obligation, in a constrained grammar. This is an RU.
- **Facts** — interface reality: routes, subjects, limits, vocabularies. Declared
  once in a manifest and *referenced* from statements, never restated.
- **Dynamics** — lifecycles and invariants, as statecharts, from which
  conformance suites are generated.

A fact restated inside a statement is the drift this framework exists to
prevent, so statements address facts by token (`{value:retention.audit_days}`)
and the tool resolves them.

### Statement grammar

One statement per RU, in EARS templates (ubiquitous, event, state, unwanted,
optional). Quantities must be bounded, and a bound is either a literal or a
resolvable manifest reference — never a vague adverb. Compound statements are
split, because a requirement with two obligations cannot be verified as one.

## 3. Enforcement

| Family | Judges | Lives in |
|---|---|---|
| `L*` | one artifact, alone or against the store | `lints/` |
| `C*` | consistency *between* artifacts | `checks/` |
| `CF*` | manifest versus what an adapter reports about the code | `conformance.py` |
| `M*` | statechart graph facts a schema cannot express | `model_rules.py` |
| `H*` | runtime write scope during packet-scoped work | `hooks.py` |

Severities are chosen deliberately: `error` stops the build, `warning` is
survivable debt that blocks only under `--strict`, and `finding` is report-only
for conditions the tool cannot adjudicate. Exit codes everywhere: `0` pass, `1`
violations, `2` tool error.

## 4. Lifecycle and gates

Draft (ULID, collision-free) → **Gate 1** sitting → activated with a permanent
id, a gate stamp, and link fingerprints → implementation → **Gate 2** human
verdict where the requirement demands one.

The two gates ask different questions and neither is inferrable from the other:
Gate 1 asks *is this what I said?*, Gate 2 asks *does the built thing achieve
the intent?* Both are recorded as data.

Five change paths exist, each deliberate: supersession (meaning changes),
re-affirmation (a referenced model changed but the meaning did not), TODO
resolution (a promised check now exists), non-normative edit (tags, typos), and
manifest impact (a fact changed, with its blast radius reported).

## 5. Language neutrality

Every *judgment* lives in the core; everything language-specific lives in a
per-stack adapter, behind pinned contracts:

| Contract | Direction | The adapter provides | The framework decides |
|---|---|---|---|
| `actual-surface` | adapter → core | an extractor: what the code exposes | what every difference means (CF rules) |
| `scanned-checks` | adapter → core | a scanner: tests and their `verifies` traces | traceability, and the new-test gate |
| `emit-request` / `emitted-files` | core → adapter → core | an emitter: the plan as idiomatic tests, returned as data | which checks exist and their identity; core writes every file |
| `check-evidence` | adapter → core | an evidence probe: what passed, what has failed | whether a check has demonstrated it can fail |
| `strip-request` / `stripped-files` | core → adapter → core | a stripper: remove trace annotations | which annotations are stale |

Each role is a declared command the core runs as an opaque black box, or an
artifact the stack's own pipeline produced. **The core never invokes a compiler,
build tool or test runner.** An adapter observes; it never judges — and it never
parses an id, which is why `verifies` is typed as free strings.

Adding a language costs an adapter with a passing compliance kit
(`rqunit adapter verify`). If it requires a core change, the contracts are
wrong: fix them rather than special-casing the language.

## 6. Where things live

```
src/rqunit/
  store.py        loader: parses, validates, hashes, resolves reference tokens
  canonical.py    THE canonicalizer — gate stamps and link fingerprints
  ids.py          permanent-id arithmetic and grammar
  status.py       computed status
  config.py       rqunit.toml; core-read keys are a closed set
  invoke.py       the one door to every adapter role
  conformance.py  manifest ↔ reported surface
  generate.py     test plans, projections, emit requests
  trace.py        traceability and the new-test gate
  doctor.py       structural health, advisory by construction
  parser/         EARS parser and reference tokenizer
  lints/ checks/  one module per rule
  interfaces/     the pinned adapter contracts
  pack/           schemas and seeds, shipped inside the package
  cli/            one module per verb
adapters/         per-stack adapters, source and compliance kits
fixtures/         pass and fail stores for every rule
```

Two directories are easy to confuse and must not be: `.claude/` is how *this
product is developed*; `src/rqunit/integrations/claude-code/` is what the
product *emits into a consumer's repository*.

## 7. Settled decisions

Closed. Re-open only with a case the reasoning did not anticipate.

1. **One file per RU.** Merge isolation under parallel drafting, per-requirement
   git archaeology, per-file immutability checks. One file per *feature* is the
   worst possible sharding key — it collides exactly where work concentrates.
2. **Permanent ids are minted at Gate 1**, the one already-serialized point,
   from the directory listing. A counter file is forbidden: it races across
   branches. Everything created *outside* a serialization point — drafts, GAPs,
   intents — carries a ULID instead, because nothing could allocate it a
   sequence. See [the identity scheme](identity-scheme-design.md).
3. **Files, not a database, as source of truth.** A database cannot be branched,
   diffed in a pull request, or worked on offline, and separating requirements
   from code is the disease being treated. A generated index for queries is
   welcome; as the store, a database is disqualified.
4. **Reviewer ids are stable handles, never emails.** The store is published
   with the repository.
5. **Status is computed, never asserted.** The tool refuses to claim a green it
   cannot prove, including admitting zero rather than flattering itself.
6. **Kinds grow by demand.** The model dialect is flat, there is no generic
   assertion DSL, and extension happens by schema revision when a real case
   arrives. Over-engineering is the failure mode this framework is most exposed
   to.
7. **Exceptions are visible data with mandatory justification** — never
   constants in tooling code, never silent. A divergence nobody can defend in
   prose is a defect wearing a waiver.
8. **The report is honest in both directions.** It explains computed-status
   vocabulary inline rather than showing a wall of zeros that reads as
   catastrophe.

## 8. Operating principles

- **Tests assert invariants, never point-in-time state.** An exact count or an
  absence-of-warnings assertion turns ordinary growth into a broken build.
- **Committed documents are timeless.** No status, counts, project history, or
  session narrative. Status belongs in tool output; history belongs in git and
  [the changelog](../CHANGELOG.md).
- **Error messages are the teaching surface.** Every violation carries a
  suggestion and a section reference. It is worth more than any tutorial, works
  in any agent runtime, and costs nothing until it fires.
- **Guides cache the law; the linter is the law.** Guidance stating a rule the
  tools do not enforce has shipped drift. Summarise, and say so.
- **A gate people learn to ignore is worse than no gate** — which is why
  `doctor` is advisory, and why an unfixable warning is a defect.
- **Generated artifacts are byte-deterministic and currency-checked**, or they
  rot invisibly.
- **One canonicalizer.** Its byte format is a published contract: changing it
  invalidates every stamp in every consumer store.

## 9. The boundary

**This repository is the product.** Projects that adopt RQUnit are consumers,
and the distinction is load-bearing and easy to violate:

- No consumer's name, domain language, service names, or filesystem paths appear
  in any artifact here — not in the spec, formats, handbook, schemas, error
  messages, or fixtures. Examples use a generic order-management domain, and a
  test enforces this over every tracked file.
- Nothing here assumes a language, framework, or repository layout. Language
  knowledge lives only in adapters, behind the pinned contracts.
- If a rule seems to need a consumer-specific fact, that fact belongs in the
  consumer's `rqunit.toml`, never in this codebase.
