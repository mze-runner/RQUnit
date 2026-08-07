---
name: spec-store
description: Operating the RU spec store and its toolchain — the rqunit lifecycle CLI (with spec-* aliases) and when each verb runs, lifecycle and gates, computed status, which files are authored vs generated, the task-packet/H1-arming workflow, and the per-area migration playbook. Load when running spec tooling, preparing a Gate 1 sitting, assembling packets, or migrating a legacy area.
---

# Operating the spec store

Store layout is spec §12.1; the authority for everything here is
the framework specification.
Which areas the store governs: the area ledger (`spec/framework/MIGRATION.md`).
For WRITING artifacts, load `ru-authoring` — this skill is about running the machinery.

Every verb runs through one CLI: `rqunit <verb>`, from anywhere at or below the store root. Repo-specific inputs — trace scan globs, diff pathspecs, literal-scan directories, adapter artifact paths — live in the committed `rqunit.toml` at the repo root (strict: unknown keys are errors, because a typo that reads as configured is worse than one that fails).

## The toolchain

| Tool | What | When |
|---|---|---|
| `rqunit lint` | Lints L1–L22 (L14 lives in `rqunit trace`) | Every spec/ change; pre-commit + CI |
| `rqunit check` | Consistency C1–C9 | Same |
| `rqunit generate all` / `check` | Regenerate / verify committed projections + conformance artifacts (constants, statechart suites, test-plan, trace-map, ru-index, surface sheets) | `all` after manifest/model/RU changes; `check` gates commits |
| `rqunit trace [--against REF]` | verifies-annotation resolver, orphan reports; `--against` = L14 gate (new untraced tests block) | CI; PRs |
| `rqunit activate batch --feature F --reviewer H` | Gate 1 activation: refuses on red, all-or-nothing, L21-gated, impact-gated, ONE commit with stamps+fingerprints | End of each Gate 1 sitting (operator-invoked; it commits by design) |
| `rqunit activate restamp --reviewer H` | Stamps for manually-activated RUs; fingerprint re-affirmation | Rare; suspect-queue resolutions |
| `rqunit activate reaffirm --model MDL-x --reviewer H` | Lawful model evolution: re-stamps active dependents of an edited model (hash + stamp + conformance regen); supersede instead when the change alters an RU's meaning | After any edit to a referenced model |
| `rqunit activate resolve --reviewer H RU-XXXX=REF… [--match S]` | Debt conversion: TODO entry → real same-type ref (store contract / scanned test id) + re-stamp; strictly strengthening, refuses removals/swaps/dangling targets | When a TODO's promised check lands |
| `rqunit impact --against REF` | Additive/mutating manifest diff + affected-RU report | Before approving manifest edits |
| `rqunit review record RU-XXXX …` | Append-only Gate 2 verdicts (ONLY entry path — agent writes to spec/reviews/ are hook-blocked) | Human verifications |
| `rqunit review guard --against REF` | Append-only guard for records + packets | CI (PRs) |
| `rqunit assemble build TASK --ru … [--arm]` / `disarm` | Materialize a task packet; `--arm` points `spec/packets/.active` at it → H1 blocks `must_not_touch` writes, H2 audits out-of-owns | Start/end of packet-scoped implementation |
| `rqunit lineage FEAT-<slug>` (or an RU id) | Feature elaboration timeline: intent sources, Gate 1 sittings, supersessions, Gate 2 records, gaps, current states. Read-only query — writes nothing | Disputes, audits, onboarding |
| `rqunit conformance` | Manifest ↔ code surfaces (CF1–CF11) from each stack's committed `actual-surface.json`. The extractor runs in the stack's own build (its test proves the artifact is current). Each artifact declares which surface families it examined; ratified exceptions live in `spec/framework/conformance-exceptions.yaml` — an extractor observes, and does not get to excuse what it observed — and still report as findings | After route/message changes; every gate |
| `rqunit doctor [--strict]` | Structural health: id gaps (an RU lost in a bad merge resolve), orphaned contracts/models/ADRs/FEATs, dangling review records, branch behind upstream (activation-collision risk). Advisory: exit 0 unless `--strict` | After merges; before a Gate 1 sitting |
| `rqunit report [--out F] [--format html\|json]` | Self-contained HTML snapshot for review audiences (coverage, status, gate activity, burn-down, health); `--format json` = the data contract. NOT a committed projection — it carries a timestamp | Before steering/management reviews |
| `rqunit index` | Just the index + surface sheets | Rarely needed directly (`rqunit generate` covers) |

Exit codes everywhere: 0 pass, 1 violations, 2 tool error. `finding` severity (C7, L20) never
affects exit.

## Authored vs generated

Authored (hand-edited, reviewed): `spec/{intent,ru,features,gaps,manifests,models,contracts,rationale}/`,
`spec/framework/{tags,actors,coverage.policy}.yaml`, MIGRATION.md.
Generated (NEVER hand-edit — `rqunit generate check` fails on drift): everything under
`spec/projections/`, `spec-conformance-tests/{src/generated,tests/generated_*}`.
Append-only (guard-enforced): `spec/reviews/`, committed `spec/packets/*.packet.md`
(re-runs version as `.v2`).

## Status is computed, never asserted

`done` = every verification provably passes (today: human entries with post-stamp Gate 2
records; mechanical pass-states arrive as conformance/trace mature). `blocked` = any TODO ref.
`failing` = stale model/manifest hash or invalid gate stamp. `debt` = human-only verification.
`suspect` = a fingerprinted link's target changed (queue: `spec/projections/suspect-queue.json`,
resolved at Gate 1 by re-affirm or supersede). Expected standing output today: 4 L21 burn-down
warnings, ~29 C7 orphan findings (the legacy bridge surfaces), 641-check L14 burn-down.

## Packet workflow (provisional until G4 validates it)

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
overrides). If two branches did activate independently, git raises an add/add
conflict; recover by reverting the losing activation commit (one atomic commit
by design — the revert restores its drafts), rebasing, and re-running
activation. Never hand-renumber. Generated artifacts (`spec/projections/`,
`spec-conformance-tests/{src/generated,tests/generated_*}`) resolve via
`.gitattributes` + regeneration, never hand-merging.

## Migrating a legacy area (master plan §7)

1. Capture the area's stories/epic verbatim as INT artifacts (provenance header: path + sha).
2. Analyst compiles ACs → draft RUs (one each), facts → manifest entries; conflicts → GAPs.
3. Replace the area's bridge-FEAT `ru:` links with real RU links (C7 burn-down shrinks).
4. Gate 1 sitting → `rqunit activate batch`; flip the area's row in MIGRATION.md in the same
   change; tombstone the legacy story files (header pointing at the INT capture).
