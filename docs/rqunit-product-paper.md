# RQUnit — Product Paper and Handover

**Status:** written 2026-07-29, at the close of industrialisation Phase II.
**Audience:** whoever continues this work — human or agent — with no prior context.
**Purpose:** a self-contained account of what RQUnit is, why it is built the way it
is, exactly where it stands, and what happens next. Nothing here assumes access to
the conversation that produced it or to any session memory.

> **Read this first if you are an agent picking the work up.** The product currently
> lives inside a consumer repository (`reevz`) and is being extracted. Section 9 is
> the extraction plan and is the immediate next task. Sections 6–8 exist so that
> settled decisions are not re-litigated: where this paper says a thing was ruled,
> treat it as ruled unless the operator reopens it.

---

## 1. What RQUnit is

RQUnit is a requirements-management framework for software built with heavy agent
participation. Its thesis is narrow and load-bearing:

> A requirement that cannot be mechanically verified is a preference. A specification
> that can drift from its code silently is decoration.

Everything in the design follows from refusing those two failure modes. Requirements
are small, individually addressable units stored beside the code they govern, in the
same version control, carrying machine-checkable links to the artifacts that prove
them. Enforcement is not advice: it is lints, consistency checks, runtime hooks, and
gates that block commits.

The framework is **domain-agnostic and language-agnostic**. It is a product in its
own right. The repository it currently lives in (`reevz`, a Rust guild-platform) is
a *consumer* — the first and so far only one — used to stress-test the framework
against a real migration. Nothing about Reevz is normative for the product, and no
framework artifact may reference it.

### What problem it actually solves

Conventional requirements tooling (DOORS, Jama, Polarion) is database-backed and
therefore lives *beside* the code, which is precisely why it drifts from the code and
needs perpetual integration effort. RQUnit inverts that: requirements live in the
repository, travel on feature branches, are reviewed in pull requests, and are
reconciled against the code by tooling that fails the build when they disagree.

The second problem it solves is agentic: an implementing agent given a whole
requirements corpus reads too much and still misses context. RQUnit assembles a
**task packet** — the complete, exact, immutable context for one task — and a
question the packet cannot answer is treated as a specification defect (a GAP), never
as licence to guess.

---

## 2. The model

### 2.1 Artifacts

| Artifact | Identity | Mutability | Holds |
|---|---|---|---|
| **INT** (intent) | `INT-XXXX` | immutable | verbatim human input; nothing paraphrased |
| **RU** (requirement unit) | `RU-XXXX` | frozen at activation; change = supersession | exactly one normative sentence |
| **FEAT** (feature) | `FEAT-<slug>` | versioned | grouping + one goal sentence; never normative |
| **Manifest** | `<service>.manifest.yaml` | Gate-1-gated edits | interface *facts*: endpoints, messages, channels, values, vocabularies |
| **MDL** (model) | `MDL-<slug>` | content-hashed | dynamics: statecharts, decision tables |
| **CT** (contract) | `CT-<slug>` | Gate-1-gated edits | a checkable *shape* (e.g. a token's exact claim set) |
| **ADR** | `ADR-<slug>` | editable prose, fingerprinted | rationale — the *why* |
| **GAP** | `GAP-<ULID>` | open → resolved | analyst-surfaced ambiguity or conflict |
| **Review record** | under `reviews/RU-XXXX/` | append-only | Gate 2 human verdicts |
| **Packet** | `TASK-XXXX.packet.md` | immutable, versioned | the exact context an agent received |

### 2.2 The four knowledge classes

The division that keeps artifacts from restating each other:

- **RU = behaviour** — what the system shall do. One EARS sentence.
- **Manifest = facts** — what exists. Declared once, referenced everywhere.
- **MDL = dynamics** — when and how state moves.
- **CT / test = proof** — what must hold, checkably.

Statements never restate facts (a lint enforces this). They *reference* them with
tokens: `{endpoint:token_refresh}`, `{value:retention.days}`, `{problem:not-found}`.
A fact changes in one place and every requirement referencing it keeps its meaning.

### 2.3 Statement grammar

Statements are EARS, exactly one normative clause, terminated by a period:

```
ubiquitous  The system shall <response>.
event       When <trigger>, the system shall <response>.
state       While <condition>, the system shall <response>.
unwanted    If <condition>, then the system shall <response>.
optional    Where <feature-condition>, the system shall <response>.
```

The shall-subject is `the system` or a service name; actors never take the shall and
must be canonical ids from a registry. Bounds must be literal (`within 5 seconds`) or
a value reference — vague quantifiers are errors.

---

## 3. Enforcement

This is the framework. Everything else is prose.

**Lints (L1–L22)** — per-artifact rules: statement parses; bounds are real; no
compound statements; source anchors resolve; verification refs resolve; model hashes
current; supersession chains acyclic and links resolve; no workflow fields; filename
matches id; tags and actors registered; FEAT goals non-normative; ≤15 constitutional
RUs; reference tokens resolve; no fact restatement; every active RU carries a valid
gate stamp; fingerprinted links flagged when targets change; coverage policy honoured;
planned surfaces backed by a not-done RU. (L14 lives in the trace stage.)

**Consistency checks (C1–C9)** — cross-artifact: duplicate/conflicting triggers;
ownership overlap between unrelated features; `must_not_touch` collisions; endpoint
uniqueness; vocabulary membership; declared error/audit emissions; orphan facts;
model vocabulary resolution; message topology.

**Conformance divergences (CF1–CF6)** — manifest versus code: declared-but-unserved,
served-but-undeclared, implemented-but-still-planned, access-tier mismatch,
declared-outbound-unpublished, published-undeclared.

**Hooks (H1/H2)** — runtime, during packet-scoped agent work: H1 blocks writes
outside the task's declared boundaries; H2 audits out-of-scope writes without
blocking. Agent writes into the review directory are denied outright — no
self-certification.

Severities: `error` blocks; `warning` reports (blocks with `--strict`); `finding` is
report-only and never affects exit. Exit codes: 0 pass, 1 violations, 2 tool error.

---

## 4. Lifecycle and gates

```
intent captured verbatim (INT)
        ↓  analyst compiles: one acceptance criterion = one RU
draft RUs (RU-draft-<ULID>)  ── ambiguity becomes a GAP, never a default
        ↓  GATE 1 — human fidelity review: "is this what I said?"
active RUs (RU-XXXX)         ── statement/scope/verification/tier FREEZE
        ↓  packet assembled → agent implements → tests carry `verifies:` traces
        ↓  GATE 2 — human goal verification: "does it achieve the intent?"
computed status
```

**Two human gates, never conflated.** Gate 1 is translation fidelity, per batch, at
activation. Gate 2 is goal verification, per human-type verification entry, recorded
through the CLI only.

**Status is computed, never asserted.** `done` = every verification provably passes.
`blocked` = a TODO ref. `failing` = stale hash or invalid stamp. `debt` = human-only
verification. `reviewed` = valid stamp plus passing post-stamp records. `suspect` = a
fingerprinted link's target changed.

### 4.1 The change paths (all five, each deliberate)

| What changes | Path |
|---|---|
| An RU's meaning | **Supersession** — new draft with `supersedes:`, anchored to new intent, activated |
| A manifest fact | Gate-1-gated edit **with an impact report**; referencing RUs keep meaning through the reference |
| A model | **`activate reaffirm`** — re-stamps active dependents whose meaning survives; supersede those whose meaning changed |
| A contract or ADR | Edit in place; dependents' fingerprints flip them **suspect** for the next sitting |
| A `TODO(...)` becoming real | **`activate resolve`** — same-type replacement, strictly strengthening, re-stamped |

Every one of these exists because its absence was a deadlock discovered in practice.
Do not remove one without understanding which deadlock it opened.

---

## 5. Language neutrality: the three pinned contracts

This is the architecture that makes RQUnit a product rather than one repository's
tooling. **Every judgment lives once, in the framework. Everything language-specific
lives in a per-stack adapter.** Three JSON contracts carry the boundary:

| Contract | Direction | The stack provides | The framework decides |
|---|---|---|---|
| `actual-surface.json` | adapter → core | an **extractor**: what the code really exposes (routes, published messages), in manifest vocabulary | what every difference *means* (CF1–CF6), including the planned-surface asymmetry |
| `test-plan.json` | core → adapter | an **emitter**: renders the plan as idiomatic tests | which checks exist, what each asserts, their identity and order |
| scanner registry | adapter → core | a **scanner**: finds tests and their `verifies` traces | traceability rules and the new-test gate |

Consequences that must be preserved:

- **Adapters never judge.** An extractor reports; it does not decide whether a
  missing route is acceptable.
- **The core never invokes a compiler.** Extraction runs in the stack's own build
  system (`cargo test`, Gradle, npm), and that stack's currency test proves its
  artifact still matches the code. This is why the core needs no language toolchain.
- **Emitters are pure functions of the plan.** Asserted by test — it is what stops a
  second language from silently asserting something different from the first.
- **Ratified exceptions travel inside the artifact**, with a mandatory substantive
  justification, and downgrade a divergence to a *reported finding* — never silence
  it. An exception nobody can defend in prose is a defect wearing a waiver.

The scanner registry is deliberately a registry of **functions**, not a
parameterized generic scanner: discovery differs structurally between stacks (Rust's
`#[test]` above a free function in `tests/`; JUnit's `@Test` on a method under
`src/test/java`), and one algorithm bent to fit both would be false generality.

---

## 6. Current implementation state

**Version:** pack v0.11.x. **Tests:** 443 passing (Python), plus Rust adapter tests.
**Language:** Python 3.12, `uv`, ~8,400 lines across 32 modules plus fixtures.

### 6.1 CLI surface (`rqunit`)

```
verification   lint · check · trace · conformance
health         doctor
reporting      report
Gate 1         activate batch | restamp | reaffirm | resolve
Gate 2         review record | guard
governance     impact
context        assemble build | disarm
history        lineage
projections    generate all | check | scan-literals · index
enforcement    hooks h1 | h2
```

Per-tool `spec-*` entry points survive as compatibility aliases; retire them at
publication.

### 6.2 Module map

```
spec_tools/
  store.py          loader: parses, schema-validates, hashes, resolves reference tokens
  canonical.py      THE canonicalizer — gate-stamp and fingerprint hashing
  status.py         computed status engine
  config.py         rqunit.toml (consumer configuration; strict on unknown keys)
  conformance.py    CF1–CF6 diff — the language-neutral judgment
  generate.py       plan_model_suite (neutral) + emit_rust_suite (Rust emitter) + projections
  trace.py          scanner registry, traceability, the new-test gate
  doctor.py         structural health (id gaps, orphans, dangling records, stale branch)
  report.py         build_data (report-data contract) + render_html
  assemble.py       task packets
  impact.py         manifest diff + affected-RU report
  hooks.py          H1/H2 scope enforcement
  lineage.py (cli)  on-demand feature timeline
  parser/           EARS parser + reference tokenizer (golden suite = the contract)
  lints/            l01–l22
  checks/           c1–c9
  interfaces/       actual-surface.schema.json, test-plan.schema.json
  cli/              one module per verb + rqunit.py umbrella
```

### 6.3 Validation to date

The framework has carried one complete service migration end to end: 410 active
requirement units, 27 contracts, 45 intent captures, 3 models, ~20 Gate 1 sittings.
That exercise found and fixed five framework defects, each same-day; every one is now
covered by a regression test.

---

## 7. Design decisions, and why (do not re-litigate)

1. **One file per RU.** Merge isolation under parallel drafting; free per-requirement
   git archaeology; per-file immutability checks. One file per *feature* is forbidden
   — it is the worst possible sharding key, colliding exactly where work concentrates.
2. **Monotonic `RU-XXXX` ids.** Rejected: dates in identifiers (duplicates provenance
   the gate stamp already owns, and can lie about which date), and per-area id ranges
   (a visible ceiling is the wrong optic for a tool meant to scale). Drafts use ULIDs,
   so drafting never collides; only *activation* allocates, and it refuses to run from
   a branch behind its upstream — the sole condition under which parallel allocation
   can collide.
3. **Files, not a database, as source of truth.** A database cannot be branched,
   diffed in a pull request, or worked on offline, and separating requirements from
   code is the exact disease this framework treats. A generated database (SQLite or
   Postgres) as a derived *index* for queries and dashboards is welcome; as the store,
   it is disqualified.
4. **Reviewer ids are stable handles, never emails.** The store is published with the
   repository. Enforced at schema and CLI level.
5. **Status computed, never asserted.** The tool refuses to claim a green it cannot
   prove — including admitting `done: 0` when mechanical pass-states are not yet
   wired, rather than flattering itself.
6. **Kinds grow by demand.** Contract kinds are a closed set (one exists), model
   dialect is flat, no generic assertion DSL. Extend by schema PR when a real case
   arrives.
7. **Exceptions are visible data with mandatory justification**, never constants in
   tooling code, and never silent.
8. **The report is honest in both directions.** It explains computed-status semantics
   inline rather than showing a wall of zeros that reads as catastrophe, and it
   glosses framework vocabulary for lay readers (`blocked` → "awaiting a promised
   check", i.e. tracked debt, not stalled delivery).

---

## 8. Operating principles learned the hard way

- **Tests assert invariants, never point-in-time state.** Asserting "zero warnings"
  or an exact count turns ordinary growth into a broken build. This rule was learned
  by breaking the first real activation, and violated twice more since — both times
  caught, both times de-pinned.
- **Committed documents are timeless contracts.** No status, no counts, no project
  history, no session Q&A, no consumer identifiers in framework documentation. Status
  belongs in tool output.
- **Error messages are the teaching surface.** Every violation carries a suggestion
  and a section reference; this is worth more onboarding than any tutorial, works for
  any agent runtime, and costs no context until it fires.
- **Skills cache the law; the linter is the law.** A skill that contains rules the
  tools do not enforce has shipped drift. Skills summarise and say so.
- **A gate people learn to ignore is worse than no gate** — hence `doctor` is
  advisory by construction.
- **Generated artifacts must be byte-deterministic and currency-checked**, or they
  rot invisibly.

---

## 9. Extraction — the immediate next task

The product currently lives inside the consumer repository: roughly 10,400 lines of
product code (8,400 Python, ~1,700 framework law and schemas, ~260 Rust extractor)
sitting in an application repo, polluting its history with commits that have nothing
to do with the application.

**Sequencing correction that matters:** extraction is *not* gated on the planned Rust
rewrite. The constraint that a rewrite must precede publication — once external
consumers hold gate stamps, byte-incompatible hashing is unfixable — applies to
**publication**, not to which repository the code lives in. So:

1. **Extract now** into a dedicated `rqunit` repository. The consumer depends on it
   as a git dependency (`uv` supports this) — no package index, no public API
   commitment yet.
2. **Rust port** happens inside that repository once semantics freeze (§10).
3. **Publish** after the port, so v1.0's hashes are the ones consumers live with.

### 9.1 The split

| Moves to `rqunit` | Stays with the consumer |
|---|---|
| all of `spec-tools/` | the store: intent, ru, features, manifests, models, contracts, gaps, rationale, reviews, packets, projections |
| framework law: spec, formats, HANDBOOK, all `*.schema.yaml` | consumer vocabularies: `tags.yaml`, `actors.yaml`, `coverage.policy.yaml`, the migration ledger, and a new `pack.yaml` version pin |
| the Rust extractor (`extract.rs` + its binary) → `rqunit-adapter-rust` | statechart shims and generated suites (these wire the consumer's services) |
| integration templates | `rqunit.toml`, agent-runtime integration files |

### 9.2 Target layout of the product repository

```
rqunit/
  README.md                what it is, install, quickstart
  HANDBOOK.md              the operator handbook — root level, daily-use document
  docs/
    ru-framework-spec.md   the law — versioned here, NEVER shipped into a consumer
    formats.md
  pyproject.toml
  src/rqunit/
    pack/schemas/          the only pack content in the wheel: what the tool needs at runtime
    …                      the modules from §6.2
    interfaces/            the pinned JSON contracts
    integrations/          emitted templates (agent runtime, CI, hooks)
  adapters/rust/           → published to the language's own registry
  fixtures/  tests/
```

The framework specification and formats reference are **not** shipped to consumers:
the consumer's contract surface is the handbook, the CLI, and error messages. The
wheel carries schemas and code; `pack.yaml` in the consumer records which pack
version their store was authored against.

### 9.3 Work items

1. **Schema packaging** (the only non-obvious one, and everything depends on it).
   Today the loader walks *up the directory tree* to find the framework directory —
   which stops working the moment the tool is an installed dependency. Schemas must
   ship inside the package and load from it; consumer vocabularies continue to load
   from the store. Well covered by the existing suite.
2. **`rqunit init`** — scaffolds a store, writes `rqunit.toml`, `pack.yaml`, seed
   vocabularies, the default coverage policy, and the shared-manifest access-tier
   seed. Detects the stack (`Cargo.toml`, `pom.xml`, `package.json`, `pyproject.toml`)
   and prints what it found; `--stack` overrides. Refuses a non-empty store; warns
   outside version control. Deliberately asks nothing else: the store root is fixed,
   and reviewer identity is per-sitting, never configuration.
3. **Consumer wiring** — the consumer repo depends on the product; hooks and CI point
   at the dependency.
4. **Rust adapter split** — extractor out to `adapters/rust`, shims stay behind.
5. **CI split** — product repo runs its own suite against fixtures; consumer CI
   installs the dependency and runs its own gates.

Estimate: about a week, risk concentrated in item 1.

**Coordination note:** the consumer's migration work is live. Extraction changes their
workflow from "the tools are in the tree" to "the tools are a dependency." Tell them
before, not during.

---

## 10. Roadmap after extraction

**Rust rewrite.** Ruled as the target: single-binary distribution across many teams'
CI images, no interpreter bootstrap, an order-of-magnitude faster store-wide analysis
at tens of thousands of requirements, and better enforcement credibility. Two
conditions attach:

- **Freeze criterion — one full migration batch completing with zero framework
  defects.** Not yet met: four framework versions shipped in the last two days and
  defects are still surfacing from live use. Porting a moving target is how rewrites
  die.
- **It must precede publication**, because gate stamps hash a canonical serialization;
  reproducing it byte-exactly is mandatory, and impossible to retrofit once external
  stores hold millions of stamps.

The port has an unusually strong safety net waiting: 443 tests, 40 fixture stores and
the golden parser suite form a differential harness — run both implementations over
every fixture and diff the JSON reports; byte-equal or it does not ship.

**Then, in order:** publication (binary plus package index); a JVM adapter (Spring
first, named and documented — the real test of whether the three contracts hold, and
it must land with *zero* core changes); Node and Python adapters; authoring verbs
(`intent capture`, `draft new`, `supersede`, `gap new`, `show`, `status`, `migrate`,
`pack upgrade`); a generated SQLite index for fast queries and cross-repo dashboards.

**Agentic onboarding** (ships with integrations): two skills — one for authoring
artifacts, one for operating the toolchain — plus exactly one agent role, the
analyst, because that is a role with different incentives rather than merely
different knowledge. Implementing agents need no special agent: the packet *is* the
onboarding. Resist an agent per lifecycle phase; the phases are already enforced
mechanically.

---

## 11. Known state and open items

- **Open decision:** none blocking. The store-scale question (directory sharding by
  id range at tens of thousands of units) is designed but not needed yet.
- **Backlog:** shim-aware generation (drop the ignore markers for models whose shim
  is registered); a merge driver documented for generated artifacts; expanding the
  pack self-consistency meta-test.
- **Consumer-side debt** (illustrative of what the framework reports honestly, not
  framework defects): a few coverage-policy warnings, a large untraced-test burn-down,
  and TODO verification refs being converted incrementally.
- **A caution for the next session:** this codebase is edited concurrently by more
  than one agent session. Check the log before assuming the tree is as you left it,
  and never reformat or "fix" a file you did not write — it is probably someone's
  work in progress.

---

## 12. If you are picking this up cold

Read in this order: this paper → `HANDBOOK.md` (operator's guide, includes the full
rule catalogue) → the framework specification (the law) → `formats.md` (every pinned
format). Then run the tool against the store: `rqunit lint`, `rqunit check`,
`rqunit doctor`, `rqunit report`. The output will teach you more about the current
state than any prose, which is the point of the design.

Start with §9.3 item 1.
