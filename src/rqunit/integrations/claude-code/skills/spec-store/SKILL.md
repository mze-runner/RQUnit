---
name: spec-store
description: Operating the RU spec store and its toolchain — the rqunit lifecycle CLI and when each verb runs, lifecycle and gates, computed status, which files are authored vs generated, the task-packet/H1-arming workflow, and the adoption playbook. Load when running spec tooling, preparing a Gate 1 sitting, assembling packets, or bringing an area under the store.
---

# Operating the spec store

Store layout is spec §12.1; the authority for everything here is
the framework specification.
For WRITING artifacts, load `ru-authoring` — this skill is about running the machinery.

Every verb runs through one CLI: `rqunit <verb>`, from anywhere at or below the store root. Repo-specific inputs live in the committed `rqunit.toml`, where any `[stacks.<name>]` table declares a stack — the tool carries no list of supported languages. Core interprets a CLOSED key set per stack (the `adapter` role declarations and `literal_scan`) and errors on a malformed one, because a typo that reads as configured is worse than one that fails. Every OTHER key belongs to that stack's adapter, is passed through untouched, and is checked against the adapter manifest's `config_keys` rather than by core — judging what `routers` means would be language knowledge, and language knowledge lives out of process.

## The toolchain

| Tool | What | When |
|---|---|---|
| `rqunit lint` | The L-family lints, one artifact at a time (L14 lives in `rqunit trace`) | Every spec/ change; pre-commit + CI |
| `rqunit check` | The C-family consistency checks, between artifacts | Same |
| `rqunit generate all` / `check` | Regenerate / verify committed projections + conformance artifacts (constants, statechart suites, test-plan, trace-map, ru-index, surface sheets) | `all` after manifest/model/RU changes; `check` gates commits |
| `rqunit trace [--against REF]` | verifies-annotation resolver, orphan reports; `--against` = L14 gate (new untraced tests block) | CI; PRs |
| `rqunit trace --strip [--all] [--apply]` | The off-ramp: remove trace annotations naming no active RU (`--all` removes every annotation, `infrastructure` markers included). DRY by default — it rewrites source you own, so nothing changes without `--apply`. Needs the stack's `stripper` role; a stack without one is reported un-strippable rather than swept silently, because a stack that can be adopted but not un-adopted is a one-way door | Off-boarding; before re-adopting onto a fresh corpus |
| `rqunit activate batch --feature F --reviewer H` | Gate 1 activation: refuses on red, all-or-nothing, L21-gated, impact-gated, ONE commit with stamps+fingerprints | End of each Gate 1 sitting (operator-invoked; it commits by design) |
| `rqunit activate restamp --reviewer H` | Stamps for manually-activated RUs; fingerprint re-affirmation | Rare; suspect-queue resolutions |
| `rqunit activate reaffirm --model MDL-x --reviewer H` | Lawful model evolution: re-stamps active dependents of an edited model (hash + stamp + conformance regen); supersede instead when the change alters an RU's meaning | After any edit to a referenced model |
| `rqunit activate resolve --reviewer H RU-XXXX=REF… [--match S]` | Debt conversion: TODO entry → real same-type ref (scanned test id / MDL id) + re-stamp; strictly strengthening, refuses removals/swaps/dangling targets | When a TODO's promised check lands |
| `rqunit impact --against REF` | Additive/mutating manifest diff + affected-RU report | Before approving manifest edits |
| `rqunit review record RU-XXXX …` | Append-only Gate 2 verdicts (ONLY entry path — agent writes to spec/reviews/ are hook-blocked) | Human verifications |
| `rqunit review guard --against REF` | Append-only guard for records + packets | CI (PRs) |
| `rqunit assemble build TASK --ru … [--arm] [--mode M]` / `disarm` | Materialize a task packet; `--arm` points `spec/packets/.active` at it → H1 blocks `must_not_touch` writes, H2 audits out-of-owns. `--mode check-authoring` assembles a packet for writing the checks BEFORE the implementation exists, and says so in the packet | Start/end of packet-scoped implementation |
| `rqunit evidence record [--from F]` | Fold a test run's observations into `spec/check-evidence/check-evidence.jsonl`, recording only firsts (first pass, first failure per check). This is the framework's evidence about its own CHECKS — never the audit record, which is the system's evidence to its operators. Without it nothing distinguishes a check that has demonstrated it can fail from one that has only ever been green (L26) | Wherever the suite runs; CI |
| `rqunit lineage FEAT-<slug>` (or an RU id) | Feature elaboration timeline: intent sources, Gate 1 sittings, supersessions, Gate 2 records, gaps, current states. Read-only query — writes nothing | Disputes, audits, onboarding |
| `rqunit conformance` | Manifest ↔ code surfaces (CF1–CF11) from each stack's declared extractor output — a committed `actual-surface.json`, or a prebuilt adapter the tool execs as a black box (it never invokes your build). The adapter is built in the stack's own build (its test proves the artifact is current). Each artifact declares which surface families it examined; ratified exceptions live in `spec/framework/conformance-exceptions.yaml` — an extractor observes, and does not get to excuse what it observed — and still report as findings | After route/message changes; every gate |
| `rqunit doctor [--strict]` | Structural health: id gaps (an RU lost in a bad merge resolve), orphaned models/ADRs, FEATs grouping no RUs, dangling review records, branch behind upstream (activation-collision risk). Advisory: exit 0 unless `--strict` | After merges; before a Gate 1 sitting |
| `rqunit report [--out F] [--format html\|json]` | Self-contained HTML snapshot for review audiences (coverage, status, gate activity, burn-down, health); `--format json` = the data contract. NOT a committed projection — it carries a timestamp | Before steering/management reviews |
| `rqunit index` | Just the index + surface sheets | Rarely needed directly (`rqunit generate` covers) |

Exit codes everywhere: 0 pass, 1 violations, 2 tool error. `finding` severity (C7, L20, L26) never
affects exit.

## Authored vs generated

Authored (hand-edited, reviewed): `spec/{intent,ru,features,gaps,manifests,models,rationale}/`,
`spec/framework/{tags,actors,coverage.policy,conformance-exceptions}.yaml`.
Generated (NEVER hand-edit — `rqunit generate check` fails on drift): everything under
`spec/projections/`, `spec-conformance-tests/{src/generated,tests/generated_*}`.
Append-only (guard-enforced by `rqunit review guard`): `spec/reviews/`, committed
`spec/packets/*.packet.md` (re-runs version as `.v2`), and
`spec/check-evidence/check-evidence.jsonl` — written only by `rqunit evidence record`,
which appends firsts and never rewrites. Evidence is added to, never edited: a
first that can be deleted proves nothing.

## Status is computed, never asserted

`done` = every verification provably passes — a human entry needs a post-stamp Gate 2 record,
a mechanical one needs conformance or trace to say so. `blocked` = any TODO ref.
`failing` = stale model/manifest hash or invalid gate stamp. `debt` = human-only verification.
`suspect` = a fingerprinted link's target changed (queue: `spec/projections/suspect-queue.json`,
resolved at Gate 1 by re-affirm or supersede).

A store under adoption carries standing warnings and findings, and that is the design: burn-down
is visible debt, not a broken build. Read the current census from the tool, never from a document
— a number written down here would be someone else's store on someone else's day.

## Packet workflow

1. `rqunit assemble build TASK-XXXX --ru RU-… --arm` — packet = the agent's COMPLETE context
   (constitutional RUs, resolved task RUs, star map, model, k=8 background, boundaries).
2. Implementing agent receives ONLY the packet. A question it cannot answer from the packet is a
   spec defect → file a GAP (never guess, never go read the store mid-task).
3. New tests carry `/// verifies: RU-XXXX` doc comments (L14 blocks untraced new tests on PRs).
4. `rqunit assemble disarm` when the task closes; the packet stays as the immutable flight record.

## Parallel work

Drafting never collides (ULID draft ids). Activation can: permanent ids come
from the local listing, so **merge drafts first, activate once** — `activate
batch` refuses from a branch behind its upstream (`--allow-stale-branch`
overrides). Segments narrow the window rather than closing it: each is its own
sequence, so two sittings in different domains cannot collide, but two in the
same one still can. If two branches did activate independently, git raises an add/add
conflict; recover by reverting the losing activation commit (one atomic commit
by design — the revert restores its drafts), rebasing, and re-running
activation. Never hand-renumber. Generated artifacts (`spec/projections/`,
`spec-conformance-tests/{src/generated,tests/generated_*}`) resolve via
`.gitattributes` + regeneration, never hand-merging.

## Bringing an area under the store

1. Capture the area's existing requirements verbatim as INT artifacts (provenance header:
   path + sha). Verbatim: an INT is the human words, never a paraphrase of them.
2. Declare the boundary FIRST — the service manifest, read off the code, reconciled with
   `rqunit conformance` before any RU cites it. An RU written against an unreconciled
   boundary is rewritten once the extractor disagrees.
3. Compile ACs → draft RUs (one each), facts → manifest entries; conflicts → GAPs.
4. Gate 1 sitting → `rqunit activate batch`; tombstone the superseded source documents with a
   header pointing at the INT capture.
