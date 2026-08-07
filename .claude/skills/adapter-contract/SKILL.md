---
name: adapter-contract
description: How language support works — the three pinned contracts (actual-surface, test-plan, scanned-checks) and the rules an adapter must obey. Load before adding a language, changing an adapter, or touching anything in src/rqunit/interfaces/ or adapters/.
---

# Language adapters

Supporting a language must cost an **adapter**, never a second copy of the
rules. That is the whole architecture, and it holds only while three boundaries
stay honest.

## The three contracts

| Contract | Direction | The adapter provides | The framework decides |
|---|---|---|---|
| `actual-surface.json` | adapter → core | an **extractor**: the routes and messages the code really exposes, in manifest vocabulary | what every difference means (CF-rules), including the planned-surface asymmetry |
| `emit-request` → `emitted-files` | core → adapter → core | an **emitter**: the plan rendered as idiomatic tests, returned as files-as-data | which checks exist, what each asserts, their identity and order; core validates the plan↔check mapping and writes every file |
| `scanned-checks.json` | adapter → core | a **scanner**: tests and their `verifies` annotations | traceability rules and the new-test gate (L14 = base-vs-head set difference) |

Schemas live in `src/rqunit/interfaces/`. They are pinned: changing one is a
revision event affecting every adapter.

## The rules an adapter must obey

**An adapter observes; it never judges.** An extractor reports that a route
exists. It does not decide whether a missing route is acceptable, whether a
tier difference is tolerable, or whether something counts as planned. Every one
of those is the framework's, so that all languages answer them identically.

**The core never invokes a language toolchain.** Extraction runs in the stack's
own build system — `cargo test`, Gradle, npm — and that stack proves its own
artifact is current with its own currency test. This is why the core needs no
compiler, and it is not negotiable: the moment the core shells out to a build
tool, it inherits every consumer's toolchain problems.

**Emitters are pure functions of the plan.** No reaching past the plan into the
store. A test asserts this, because purity is what stops a second language from
silently asserting something different from the first.

**Check identity comes from the plan**, never from parsing emitted source. That
mistake has already been made here once: deriving identity by regexing emitted
code also matched a helper function and mapped a non-test into the trace map.

**Exceptions are data in the artifact**, with a substantive justification, and
the framework reports them as findings. An adapter never suppresses a
divergence, and a justification nobody could defend in prose is a defect
wearing a waiver.

## Adding a language

1. **Extractor** → emits `actual-surface.json`. Idiomatic discovery for the
   stack (annotation scan, router table, framework introspection) — no
   pretence of a universal AST.
2. **Currency test** in the stack's own suite: regenerate, compare to the
   committed artifact, fail with the command that fixes it.
3. **Emitter** → an `emit-suite` command reading the emit request (plan +
   constants + passthrough options) on stdin and answering with files-as-data
   plus the plan-id → check-id mapping. Core writes the files.
4. **Scanner** → a `scan-checks` command (or pipeline-produced artifact)
   emitting `scanned-checks.json`: the tests a tree carries and what each
   one's trace annotation claims. Core derives newness by set difference.
5. **Config** → a `[stacks.<name>]` block in the consumer's `rqunit.toml`.

The contract pins the scanner's *output shape*, never its algorithm.
Discovery differs structurally between stacks; one algorithm bent to fit them
all would be false generality, and the seam exists precisely so each language
can be honest about its own shape — out of process, in its own idiom.

## The acceptance test for a new language

**It must land with zero changes to the core.** If supporting it requires
touching the diff logic, the plan derivation, or the traceability rules, the
contracts are wrong — fix the contracts rather than special-casing the
language. A core change smuggled in beside an adapter is the exact failure this
architecture was built to prevent.
