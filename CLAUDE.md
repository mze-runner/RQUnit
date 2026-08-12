# RQUnit

## What this is

RQUnit is a requirements-management framework for software built with heavy agent
participation, distributed as a CLI (`rqunit`). Its thesis:

> A requirement that cannot be mechanically verified is a preference. A specification
> that can drift from its code silently is decoration.

Requirements are small, individually addressable units stored beside the code they
govern, in the same version control, carrying machine-checkable links to the
artifacts that prove them. Enforcement is not advice — it is lints, consistency
checks, runtime hooks, and gates that block commits.

**This repository is the PRODUCT.** Projects that adopt RQUnit are *consumers*. The
distinction is load-bearing and easy to violate:

- No consumer's name, domain language, service names, or filesystem paths may appear
  in any artifact here — not in the spec, formats, handbook, schemas, error messages,
  or fixtures. Examples use a generic domain (order management).
- Nothing here may assume a language, framework, or repository layout. Language
  knowledge lives only in adapters, behind the three pinned contracts (below).
- If a rule seems to need a consumer-specific fact, that fact belongs in the
  consumer's `rqunit.toml`, never in this codebase.

---

## Layout

**Authority order** where documents disagree: `docs/ru-framework-spec.md` wins over
`docs/formats.md`, which wins over `HANDBOOK.md`, which wins over this file. The
handbook is a guide and says so; the spec is normative.

---

## Commands

`/check` runs every gate at once (suite, CLI smoke, fixture-store health, adapter
build). Exit codes everywhere: `0` pass, `1` violations, `2` tool error. `finding`
severity never affects exit.

## Working aids

Load the skill that matches the task — each encodes the sequence and the failure
mode that task actually has.

`@product-reviewer` reviews a change against the five failure modes this codebase
actually suffers from. Use it before committing anything non-trivial.

**Do not confuse `.claude/` with `src/rqunit/integrations/claude-code/`.** The first
is how *this product is developed*; the second is templates the product *emits to
consumers*. Editing one when you meant the other is the easiest mistake here.

---

## Behavioral rules

- **Do exactly what is asked — nothing more.** Do not delete, rename, refactor, or "improve" anything not explicitly requested.
- **Surface assumptions before acting.** If a request has multiple interpretations, state them and ask. Do not pick silently.
- **Surgical changes only.** Every changed line must trace directly to the request. Mention unrelated issues; never fix them unilaterally.
- **Confirm before destructive actions.** Deleting branches, force-pushing, dropping data — always state the action and wait for explicit approval.
- **Debugging: logs before theories.** When investigating a runtime failure, read all available logs first. If logs are missing for any layer in the call chain, add instrumentation and ask the user to re-run — do not form hypotheses from silence. Never apply a fix before the failure point is isolated to a specific file and line. Follow the `debug-protocol` skill for the full procedure.
- **New crate → explicit justification required before adding.** The allowed-crates tables are in the `cargo-features` skill.
- **Config files (`Settings.toml`, `Settings.local.toml`, `.env`) are gitignored everywhere** — `Settings.example.toml` is the only committed config artifact; update it in the same commit whenever a field is added or removed.

---

## Hard rules

Each of these was learned by paying for its absence. They bind agents and humans
equally.

1. **Documentation is timeless.** No status, counts, dates, roadmap position, project
   history, or session narrative in committed product documentation. Status belongs
   in tool output; history belongs in git. Dated design papers under `docs/` are the
   sole exception, and must announce their date.

2. **Tests assert invariants, never point-in-time state.** Never assert an exact
   count, an exact id list, or the absence of warnings. Visible debt is by design;
   pinning it turns ordinary growth into a broken build. Assert the property ("the
   bucket exists and never overlaps the burn-down"), not the census.

3. **Every rule ships with pass and fail fixtures**, and the fail store must be red
   for that rule's reason alone. A rule without a fail fixture is untested.

4. **One canonicalizer.** Gate stamps and link fingerprints hash through the single
   canonical implementation — three implementations of "canonical" is how canonical
   dies. Its byte format is a published contract: changing it invalidates every stamp
   in every consumer store.

5. **Generated artifacts are byte-deterministic and currency-checked.** No timestamps
   in committed output. Regeneration must byte-match or the gate fails — that is both
   the staleness rule and the hand-edit ban.

6. **Error messages are the teaching surface.** Every violation carries an actionable
   suggestion and a section reference. This is worth more than any tutorial, works in
   any agent runtime, and costs nothing until it fires. Message quality is asserted.

7. **Adapters never judge; the core never invokes a language toolchain.** An
   extractor reports what the code exposes; the framework decides what a difference
   means. The core may exec a *declared, prebuilt* adapter command as an opaque
   black box behind a pinned schema — but it never runs a compiler, build tool, or
   test runner: building the adapter is the stack's own build system's job, and a
   missing binary is a config error naming both fixes (build it, or use artifact
   mode). Emitters are pure functions of the emit request — asserted, because that
   is what stops a second language from silently asserting something different
   from the first.

8. **Kinds grow by demand.** Contract kinds are a closed set; the model dialect is
   flat; there is no generic assertion DSL. Extend by schema PR when a real case
   arrives, never speculatively. Over-engineering is the failure mode this framework
   is most exposed to.

9. **Exceptions are visible data with mandatory justification** — never constants in
   tooling code, never silent. A ratified divergence is *reported* as a finding with
   its reason attached; an exception nobody can defend in prose is a defect wearing a
   waiver.

10. **Skills and guides cache the law; the linter is the law.** Guidance stating a
    rule the tools do not enforce has shipped drift. Summarise, and say so.

---

## Architecture: the three pinned contracts

Language neutrality rests entirely on these. Every judgment lives once, in the
framework; everything language-specific lives in a per-stack adapter.

| Contract | Direction | Stack provides | Framework decides |
|---|---|---|---|
| `actual-surface.json` | adapter → core | an **extractor**: what the code really exposes | what every difference means (CF-rules), including the planned-surface asymmetry |
| `emit-request` → `emitted-files` | core → adapter → core | an **emitter**: renders the plan as idiomatic tests, returned as files-as-data | which checks exist, what each asserts, their identity and order; core validates the plan↔check mapping and writes every file |
| `scanned-checks.json` | adapter → core | a **scanner**: finds tests and their `verifies` traces | traceability rules and the new-test gate (L14 = base-vs-head set difference over the observations) |

Every role runs out of process behind its pinned schema — a declared command
core execs as a black box, or an artifact the stack's pipeline produced. The
contract pins the *output shape*, never the algorithm: test discovery differs
structurally between stacks, and one algorithm bent to fit all of them would
be false generality.

---

## Changing the framework

- **The spec and formats are normative.** Changes to them are schema-revision events,
  not edits: bump the pack version, state what changed in the status line, and update
  every dependent artifact in the same change (schema, rule, fixtures, handbook).
- **Schema and grammar must agree.** A shape the schema admits but the grammar cannot
  reference is a defect; a meta-test guards this. Extend both together.
- **Adding a rule** = module + pass/fail fixtures + handbook catalogue entry + spec
  line. Rules are numbered within their family and never renumbered.
- **Adding a language** = an extractor, a scanner, an emitter, and a manifest with
  a passing compliance kit (`rqunit adapter verify`). If it requires a core change,
  the contracts are wrong — fix them rather than special-casing.

---

## Working in this repo

- Validation happens against a reference consumer repository — a real migration, not
  a toy — but that repository is *not* part of this product, and its content must
  never leak into artifacts here. Fixtures are the only stores this repo contains.
- Prefer `?` over `unwrap()`/`expect()` in adapter library code; panics belong in
  test targets and in a build tool's entry point, where the message is the interface.
- This codebase may be edited by more than one agent session. Check the log before
  assuming the tree is as you left it, and never reformat or "fix" a file you did not
  write — it is probably someone's work in progress.

**Orientation for a fresh session:** read `docs/rqunit-product-paper.md` first —
what the product is, how it is built, and which decisions are settled and why —
then `HANDBOOK.md`, then the spec. Then run the tool against a fixture store: the
output teaches the current state better than prose, which is the point of the
design.
