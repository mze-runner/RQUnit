# Requirement Unit Framework — Operator's Handbook

How to navigate and use the requirements framework day to day — through its
lifecycle CLI, `rqunit` — plus the full catalog of rule codes (L*, C*, H*, M*).
This document is a *guide*: where it disagrees with
[ru-framework-spec.md](ru-framework-spec.md) or [formats.md](formats.md),
those win.

---

## 1. Orientation — what lives where

```
spec/
  framework/     what you author or tune: coverage policy, actors/tags
                 vocabularies, and pack.yaml (the pack version this store was
                 authored against). Schemas ship inside the tool, never here;
                 consumers migrating an existing corpus keep an area-ownership
                 ledger here (MIGRATION.md)
  intent/        INT-<ULID> — verbatim captured human intent; immutable, append-only
                 (a store adopted earlier may carry four-digit INT-XXXX ids; both
                 forms are legal permanently)
  ru/            one file per Requirement Unit (the normative statements)
  features/      FEAT-* — grouping + one goal sentence; never normative
  manifests/     per-service interface facts + shared.manifest.yaml
  framework/     vocabularies, coverage policy, ratified conformance divergences
  models/        MDL-* statecharts (dynamics; conformance suites are generated)
  gaps/          GAP-* open ambiguities/conflicts (blocking ones hold activation)
  rationale/     ADR-<slug>.md decision records — the WHY behind requirements,
                 linked from RUs via rationale_ref (format: formats §10)
  reviews/       append-only Gate 2 verdicts (written ONLY via `rqunit review`)
  packets/       materialized task contexts; immutable, re-runs version .v2
  check-evidence/  append-only ledger — which checks have been observed
                 failing (written ONLY via `rqunit evidence record`)
  projections/   GENERATED, never hand-edit: ru-index.json, test-plan.json,
                 trace-map.json, orphans.{md,json}, suspect-queue.json,
                 surface-sheets/, scope-audit.jsonl
rqunit.toml        consumer configuration (repo root): any [stacks.<name>]
                   table declares a stack and its adapter roles. The store
                   layout itself is never configured (§12.1). Missing file =
                   no stacks (store-only verbs need none); malformed core-read
                   keys are errors, adapter-owned keys pass through
rqunit             the CLI — installed, run from anywhere in the store
<conformance>/     generated conformance suites + the manifest↔code reconciler
                   live in the consumer's application workspace (language-specific)
```

**Finding things:** search `spec/projections/ru-index.json` (never grep the
`ru/` directory — the index is the query surface); skim a service's interface
at `spec/projections/surface-sheets/<service>.md`; the migration burn-down is
`spec/projections/orphans.md`.

**Reading an RU file:** `statement` is the only normative sentence. `verification`
says how it's proven (§4 below). `scope.owns`/`must_not_touch` are repo globs the
H1 hook enforces during packet-scoped work. `source_ref` anchors into the INT it
was compiled from. `gate1_stamp` + `link_fingerprints` are tool-written — hand-
authoring them is pointless (L19/L20 recompute) and editing the stamped fields
is caught mechanically.

## 2. The toolchain — the `rqunit` CLI

Run `rqunit <verb>` from anywhere at or below the store root. Repo-specific
inputs (trace scan globs, conformance-crate location) come from `rqunit.toml`
at the repo root — the tools carry no consumer paths in code.

| Command | Purpose | Typical moment |
|---|---|---|
| `rqunit init [--stack S]` | scaffold a store: directories, seed vocabularies, coverage policy, shared manifest, pack pin, `rqunit.toml`, and the agent-runtime templates into `.claude/`. Reports the stack it detected; refuses a non-empty store; never overwrites a runtime file the consumer already has | once, at adoption |
| `rqunit init --refresh-integrations` | rewrite the agent-runtime templates and touch nothing else. They teach the current vocabulary, so a store on a newer tool with older templates is being taught the wrong one | after upgrading the tool |
| `rqunit lint [--only L3]` | lints L1–L27 + the M dialect family, and `rqunit.toml` itself — a config the loader rejects is a `CONFIG` error here, not a tool error somewhere else, and a retired key still sitting where core used to read it is a `CONFIG` warning naming its successor | after any spec/ edit |
| `rqunit check [--only C4]` | consistency C1–C16 | same |
| `rqunit generate all` / `check` | (re)build / verify committed projections + generated conformance artifacts | after manifest/model/RU changes; `check` runs in every gate |
| `rqunit trace [--against REF]` | RU↔test traceability + orphan reports; `--against` = the L14 diff gate | CI; before PRs |
| `rqunit trace --strip [--all] [--apply]` | the off-ramp: remove trace annotations naming no active RU (`--all`: every annotation, `infrastructure` markers included). Dry unless `--apply` — it rewrites source you own. Needs the stack's `stripper` role; a stack without one is reported un-strippable, never swept silently | off-boarding; before re-adopting onto a fresh corpus |
| `rqunit conformance` | manifest ↔ code surfaces (CF1–CF11) — reads each stack's declared extractor output (a committed artifact, or a prebuilt adapter core execs as a black box); never invokes a language toolchain | after changing routes/messages; every gate |
| `rqunit doctor [--strict]` | structural health: permanent RUs git records as deleted and never restored, runway left before each RU **segment's** ceiling **and** the ceiling on any DECIMAL intent ids an early store carries (nothing allocates an intent id, so nothing refuses at that wall — capturing the next one as `INT-<ULID>` clears it, and the warning stops once a store has), orphaned artifacts, dangling review records, a branch stale enough to make activation collide, and adapter roles whose `cmd` resolves nowhere (a path that works only on the machine that wrote it). Advisory — exit 0 unless `--strict` | after merges; before a Gate 1 sitting |
| `rqunit evidence record [--from F]` | fold a test run's observations into `spec/check-evidence/check-evidence.jsonl`, recording only firsts. Without it nothing can tell a check that has demonstrated it can fail from one that has only ever been green (L26) | wherever the suite runs; CI |
| `rqunit adapter verify --stack <name>` | the adapter compliance kit: every declared role runs against its fixed kit input — byte-deterministic, schema-valid, matching the committed expectation, under the stdio exit contract | adapter development; the adapter's own CI |
| `rqunit report [--out F] [--format html\|json]` | a self-contained HTML snapshot for review audiences — coverage, status, verification completeness, Gate activity, burn-down, health. `--format json` emits the underlying data contract | before a steering review; on demand |
| `rqunit activate batch --feature F --reviewer H` | Gate 1 activation (atomic, refuses on red, commits) | end of a Gate 1 sitting |
| `rqunit activate restamp --reviewer H` | stamps for manual activations; suspect-link re-affirmation | rare |
| `rqunit activate reaffirm --model MDL-x --reviewer H` | the lawful model-evolution path: re-stamp active dependents of an edited model (new hash, new stamp, regenerated conformance) | after any edit to a referenced model |
| `rqunit activate resolve --reviewer H RU-XXXX=<test id> [--match S]` | debt conversion: replace a TODO verification entry with a real, scanned test id and re-stamp — strictly strengthening, never a removal or swap | when a check a TODO promised comes into existence |
| `rqunit impact --against REF` | additive vs mutating manifest diff + affected RUs | before approving manifest edits |
| `rqunit review record RU-XXXX --verdict … --criterion … --reviewer H` | append-only Gate 2 verdict | human verifications |
| `rqunit review guard --against REF` | append-only guard (reviews + packets) | CI, PRs |
| `rqunit assemble build TASK --ru … [--arm] [--mode M]` / `disarm` | materialize a task packet; arm/disarm the scope hooks. `--mode check-authoring` assembles a packet for writing the checks BEFORE the implementation exists | packet-scoped implementation |
| `rqunit lineage FEAT-<slug>` (or an RU id) | print a feature's elaboration timeline — intent sources, Gate 1 sittings, supersessions, Gate 2 records, gaps, current unit states. Read-only query; writes nothing | disputes, audits, onboarding |
| `rqunit index` | just the index + surface sheets | rarely (`rqunit generate` covers) |
| `rqunit hooks h1/h2 --path P` | the scope-hook logic (wired into the operator's agent runtime) | not run by hand |

**Exit codes everywhere:** 0 = pass (warnings allowed unless `--strict`),
1 = violations, 2 = tool error. `finding`-severity output NEVER affects exit.

**Reviewer ids are stable handles (e.g. a VCS username), never emails** —
schema and CLIs reject `@`; the handle→person mapping lives outside the store.

## 3. Daily recipes

**Add a requirement (new feature, `ru` area).** Intent is captured verbatim as
a new `spec/intent/INT-<ULID>.md` → the analyst compiles draft RUs
(`RU-draft-<ULID>`), manifest entries, and GAPs → you hold a **Gate 1 sitting**
(read drafts beside their INT anchors, triage gaps, approve manifest impact
reports) → `rqunit activate batch` does the rest in one commit. Activation is
simulate-then-write: the tool validates the SIMULATED post-activation store
(drafts counted as active — the only moment draft-blind checks see them)
before touching any file, and if the commit gate still refuses, every written
file is rolled back — the store never strands mid-operation. Consumer
pipelines typically automate this sequence end to end.

**Choose a segment.** Segments are optional and the store starts with none, so
the first question is whether you want them at all. They partition *allocation*
— `RU-ORD-0001` and `RU-AUTH-0001` are separate sequences — and nothing else:
every rule stays store-wide, because a domain that could contradict another
unnoticed is exactly what a single shared store exists to prevent.

Mint from the axis that changes slowest. Epics and capabilities belong in `feature`
and `tags`, where re-cutting costs nothing and `ru-index.json` can query across
them; a segment is a **domain**, and it is the one name in this store that can
never be corrected — renaming one is a mass supersession, so a name is chosen
once and lives with the business. "Order management" survives a reorganisation;
"the checkout squad" and `service-orders` do not. A requirement that governs
everything belongs to no domain and stays unsegmented, which is what the
constitutional tier already looks like.

**Change an existing requirement.** Never edit an active RU's statement/scope/
verification/tier — L19 catches it as post-review mutation. Write a new draft
with `supersedes: RU-XXXX`, anchor the *reason* as new intent, activate. Tags
and typo fixes to non-normative fields are the only legal in-place edits.

**Change a manifest fact.** Additive (new entry) or mutating (changed/deleted —
silently changes every frozen RU referencing it). Both pass Gate 1; mutating
ones need the `rqunit impact` report at approval. Checks read bounds from the
manifest (generated constants), so a gated change fails stale tests loudly.

**Report to a review audience.** `rqunit report` writes a single
self-contained HTML file (no external assets, prints cleanly) covering
governed-requirement counts, Gate 1 fidelity review, verification
completeness per feature and area, gate throughput, the burn-down counters,
and structural health. Every figure is computed by the same engines that gate
commits — the report cannot disagree with the tooling, and it states plainly
that `done` requires provable passes rather than implying green. It is **not**
a committed projection (it carries a generation timestamp); regenerate it on
demand. `--format json` emits the data contract for dashboards.

**Work in parallel without colliding.** Drafting is collision-free by
construction: draft ids are ULIDs, so any number of people on any number of
branches can author simultaneously and merge cleanly. The one collision point
is *activation*, because permanent ids are allocated from the local directory
listing — two branches that each activate before merging allocate the same
ids. So: **merge drafts first, activate once.** `activate batch` refuses to
run from a branch behind its upstream for exactly this reason
(`--allow-stale-branch` overrides); `rqunit doctor` reports the same staleness
before you convene a sitting.

**Recover from a parallel activation.** If two branches did activate
independently, git surfaces it as an add/add conflict on `spec/ru/RU-XXXX.yaml`
— never a silent overwrite. Do NOT hand-renumber (that strands manifest `ru:`
links, `supersedes` targets, `verifies:` annotations, and review-record
directories). Instead: **revert the losing branch's activation commit** — it is
one atomic commit by design, and reverting restores its draft files exactly —
then rebase onto the merged branch and re-run `rqunit activate batch`. Fresh
ids, no surgery; the human Gate 1 judgment stands, only the stamp timestamp
moves. Afterwards run `rqunit doctor`: it compares what git records as deleted against
what the store still carries, so an RU dropped by the resolution rather than
reallocated is reported by name.

**Resolve a TODO ref.** When the check a `TODO(…)` promised now exists, run
`rqunit activate resolve --reviewer <handle> RU-XXXX=<ref> …` — batch pairs,
one ceremony. The target must exist (a scanned test id)
and replaces only a TODO entry of ITS type; with several same-type TODOs,
`--match <substring>` selects by description. The verb refuses weakening in
every form — removing entries, swapping real refs, unresolvable targets —
those remain supersession territory. Prior Gate 2 records stop counting
(the new stamp postdates them).

**Declare a wire shape.** A shape is a MANIFEST fact — there is no separate
contract artifact, because a manifest already is one. A surface declares its
census inline (`inbound`/`outbound`, formats §13); a structure hidden behind an
encoding boundary — a token's claims inside `access_token: string` — is a
shared `artifacts` entry (formats §16) that a field names with `artifact:`.
RUs never restate a census: they ADDRESS it with a token
(`{endpoint:get_order.outbound.cost_basis}`, `{artifact:jwt-access-token.iss}`)
and prove it with a test. Editing a manifest flips its dependents suspect (L20)
for the next sitting.

**Record the *why* behind a requirement.** Write
`spec/rationale/ADR-<slug>.md` (headings per formats §10: Context, Decision,
Alternatives, Consequences) and set `rationale_ref: ADR-<slug>` on the RU;
packets then carry the decision verbatim (section 3). ADRs stay editable
prose — but once an activated RU fingerprints one, an edit flips that RU
suspect (L20), resolved at the next Gate 1 sitting. `rationale_ref` is
outside the stamp hash, so adding it to an already-active RU is a legal
non-normative edit; `rqunit activate restamp` records the fingerprint.

**Change a model.** Edit the statechart, then hold a mini Gate 1 sitting:
`rqunit activate reaffirm --model MDL-<id> --reviewer <handle>` prints every
active dependent's statement — for each, judge *re-affirm* (the statement's
meaning survives the change; the tool updates its `model_hash`, re-stamps
under your id, regenerates conformance) or *supersede* (the meaning changed;
exclude it via `--ru` on the kept set and write a superseding draft). Prior
Gate 2 records for re-affirmed RUs stop counting — they judged work verified
against the old model. Superseded RUs keep historical hashes untouched.
Hand-editing a hash without the ceremony is an L19 error.

**Run an implementation task from a packet.** `rqunit assemble build TASK-… --ru … --arm`;
give the agent ONLY the packet. Questions the packet can't answer are GAPs, not
guesses. New tests carry the language's `verifies` trace annotation (formats §5). `disarm` when done; the packet
stays as the immutable flight record of exactly what the agent saw.

**Author the checks first (recommended for anything you intend to prove).**
`rqunit assemble build TASK-… --ru … --mode check-authoring` assembles the same
packet plus a discipline section: write the checks from the statements, do not
read the files the task owns, run them, and expect RED. Then
`rqunit evidence record` puts that first red on the ledger. A check written
against an implementation it has already read can assert that implementation's
shape and never fail — it reads as coverage and proves nothing. Nothing gates
the reading; what makes the discipline checkable is the evidence: a check that
was only ever green is reported by L26 (§6.8) whatever the packet instructed.
Assemble the implementation packet afterwards, in the default mode.

**Migrate a legacy area** (consumers adopting over an existing requirements
corpus; ownership tracked in an area ledger such as MIGRATION.md): capture the
legacy prose verbatim as INT → compile one RU per acceptance criterion →
replace the area's bridge-FEAT links → one Gate 1 sitting activates and flips
the ledger row → tombstone the legacy files. The C7 orphan count is the
progress bar.

**Re-adopt onto a fresh corpus** (the store was emptied and adoption restarts):
the previous corpus's `verifies` annotations are still in your tests, naming ids
that no longer exist. Clear them BEFORE the first activation — ids are allocated
`max + 1` from `spec/ru/`, so a restarted corpus walks back into the id space
those annotations occupy, and a stale annotation stops erroring and starts
resolving to an unrelated requirement. `rqunit trace --strip` (dry) then
`--apply` removes exactly the orphans; the live links you have already
re-pointed survive, so it is safe to re-run at any point in the migration.

**Off-board entirely**: `rqunit trace --strip --all --apply` returns the tests
to the state adoption found them in; `spec/`, `rqunit.toml`, the generated
artifacts, and the emitted `.claude/` templates are directories you delete.
Commit the strip separately from the deletions — one reviewable diff per idea.

**Resolve a suspect link** (`suspect-queue.json` non-empty): a fingerprinted
target changed after review. Binary choice at the next Gate 1 sitting:
re-affirm (`rqunit activate restamp` refreshes the fingerprint under your handle)
or supersede the RU whose rationale died.

## 4. Verification & computed status

Verification types: `test` (a language-specific stable id per formats §5, e.g.
`<package>::<file-stem>::<fn>`), `model` (MDL-* with a
content hash; conformance suites are generated, never hand-written),
`human` (explicit deferred judgment → Gate 2 records). A missing check is
`ref: TODO(<description>)`.

Model conformance is *diagram-as-oracle*: the generated suite (one test per
transition, one rejection per undeclared state/event pair, one probe per
invariant) drives a hand-owned **shim** that wires the real implementation —
never a parallel re-implementation of the lifecycle. Registration is a claim
the store records in `spec/framework/shims.yaml`, checked by C15, and it has
consequences: until a model's shim is registered its generated tests stay
ignored-with-reason (pending, not green), its verification contributes **zero**
depth to the coverage policy (L21 — the mechanical minimum and the
`types_all`/`types_any` clauses alike), and the report counts it as
`model (pending shim)` rather than beside suites that execute. That is the
last place declared depth could exceed provable depth — a suite that cannot
execute is not depth.

Generation runs in two halves. The framework derives a **test plan** —
`spec/projections/test-plan.json`, a committed, language-neutral statement of
what must be checked — and a per-stack **emitter** renders it as idiomatic
tests. Emitters render; they never decide. Check identity comes from the plan,
so traceability survives regeneration and is identical across languages.

The same split runs through the whole conformance layer, in pinned contracts
each role serves **out of process**: a stack's **extractor** reports what the
code exposes (`actual-surface.json`), the framework diffs it against the
manifests (CF1–CF11); a stack's **scanner** reports the tests a tree carries
and their `verifies` traces (`scanned-checks.json`), the framework owns
traceability and L14's set-difference definition of "new"; the framework
plans what must be checked, a stack's **emitter** renders the emit request as
files-as-data (`emitted-files`) that core validates against the plan's census
and writes itself. Each role is a declared command core execs as a black box,
or an artifact the stack's own pipeline produced — core never invokes a
language toolchain. The adapter's manifest (`adapter.yaml`) declares its
roles, the passthrough config keys it reads, and the compliance kit
`rqunit adapter verify` runs. Everything language-specific lives in those
per-stack pieces, and every judgment lives in the framework — so supporting a
language costs an adapter, never a second copy of the rules, and never a core
change.

**Where an adapter comes from, and where you point at it.** Core never builds
one and never invokes a language toolchain, so obtaining the binary belongs to
your build the way any other dev tool does. Two shapes are supported, and the
difference matters the moment a config is committed:

| Shape | Declare | When |
|---|---|---|
| PATH | `cmd = ["rqunit-scan-checks"]` | the default. Install it wherever your team and CI already install tools — this is the only shape that is correct on every machine rather than on the one that wrote it |
| in-repo | `cmd = ["tools/rqunit/scan-checks"]` | a path under the STORE root, built or vendored by your own pipeline |
| artifact | `artifact = "path/to.json"` | no binary at all: an earlier pipeline step already looked and wrote down what it saw |

A path outside the store — a sibling checkout of the adapter's source — resolves
for its author and for nobody else, CI included; `rqunit doctor` reports a `cmd`
that resolves to neither a file under the store nor PATH. Artifact mode is the
zero-dependency option for every role **except the stripper**, whose answer
depends on a request core computes moments earlier, so a committed file would be
an earlier run's edits applied to today's source. Off-boarding therefore needs a
working command: if being able to leave matters to you, wire the stripper while
adoption is easy rather than when you want out.

An extractor's repo-specific inputs — which router functions mount at which
prefix and tier, where subject constants live, which manifest service the
artifact is keyed by — are `[stacks.*]` config in `rqunit.toml`, never
constants in adapter source. Composition is a fact about one repository, not
about a language or a web framework, and an extractor that guessed one would
report a surface nobody declared.

Status is computed, never asserted:

| Label | Meaning |
|---|---|
| `done` | every verification provably passes (v1: human entries with post-stamp Gate 2 records; mechanical pass-states arrive as conformance/trace mature) |
| `blocked` | any TODO ref |
| `failing` | stale model/manifest hash, or gate-stamp mismatch |
| `debt` | verification is human-only (watched metric) |
| `reviewed` | valid stamp ∧ all human criteria have passing post-stamp records |
| `suspect` | a fingerprinted link's target changed (orthogonal — a done RU can be suspect) |

**Two human gates, never conflated:** Gate 1 = translation fidelity ("is this
what I said?"), per feature batch, at activation. Gate 2 = goal verification
("does the built thing achieve the intent?"), per human-type entry, recorded via
`rqunit review`.

## 5. Rule catalog

Severities: **error** (blocks, exit 1) · **warning** (reported; blocks only
with `--strict`) · **finding** (report-only, never affects exit).

### Lints (`rqunit lint`, store-scoped)

| Code | Severity | What it enforces |
|---|---|---|
| L1 | error | statement parses under its declared syntax (the 5 EARS templates / gherkin); message carries the nearest-template diagnosis |
| L2 | error | Scope: the bound slot only (quantities, e.g. "within __", "for __ days"). A bound must be a literal `number unit` or a `{value:…}` reference; vague quantifiers are errors (wordlist is data: `vague_terms.yaml`). Scans authored prose only: reference-token spans are masked first — `{problem:too-many-requests}` never trips `many` — while bare, un-braced identifiers still scan. Token resolution is L15, restatement is L17 |
| L3 | error | compound statements: >1 shall-clause, semicolon-joined, or an "and <verb>" conjunct (verb lexicon is data) — split into one RU each |
| L4 | error | `source_ref` targets an existing INT and the line anchor fits the file |
| L5 | error | verification non-empty; non-TODO `model` refs resolve to a store model (test depth belongs to `rqunit trace`) |
| L6 | error | recorded `model_hash` matches the current model file — stale hash = the RU is FAILING until conformance regenerates ("green against a stale model is red"). Active and draft RUs only: superseded/retired hashes are provenance, and the lawful refresh is `rqunit activate reaffirm` |
| L7 | error | cross-artifact links: supersession chains acyclic, targets exist and aren't retired; `rationale_ref` resolves to a `spec/rationale/` file |
| L8 | error | forbidden workflow fields (priority, estimate, assignee, role, permission, sprint, iteration) absent |
| L9 | error | no non-draft RU references a draft ULID (activation must rewrite them; the `draft_id` provenance field is exempt) |
| L10 | error | every tag exists in `tags.yaml` first |
| L11 | error | FEAT goals carry no normative keywords (shall/must/should, uppercase MAY) |
| L12 | error | the parsed EARS actor is a canonical `actors.yaml` id; aliases rejected with the rename; unknown hyphenated role-names flagged |
| L13 | error | ≤15 active constitutional RUs store-wide; violation lists all members |
| L14 | error (base-vs-head) | *lives in `rqunit trace`*: tests NEW against `--against REF` (set difference over the scanner's observations) without a `verifies` trace (or the audited `infrastructure` marker) block; pre-existing untraced tests are burn-down |
| L15 | error | every statement reference resolves; malformed tokens are a distinct class; qualified refs resolve ONLY in the named manifest and only to surfaces/problem/audit |
| L16 | error | a service-manifest key shadowing a shared key — resolution must stay unambiguous |
| L17 | error | fact restatement: literal paths/subjects/wire-types/registered values (≥10 for numbers) in a statement instead of a reference (P8's teeth) |
| L18 | error | every manifest surface entry's `ru:` link resolves to an existing RU/FEAT |
| L19 | error | every active RU has a `gate1_stamp` whose hash matches its current normative fields — the freeze made mechanical; mismatch = edited after review |
| L20 | finding | a `link_fingerprints` target changed → the RU enters the suspect queue (re-affirm or supersede at Gate 1) |
| L21 | draft: error · active: warning | coverage policy (`coverage.policy.yaml`, first match wins): constitutional needs ≥2 mechanical verifications; `security` and `audit` need `binds_shape` — a statement token addressing a declared census or artifact, which reads the STATEMENT rather than `verification`. Under-covered drafts cannot activate; actives are burn-down |
| L22 | error | a `planned: true` surface must be governed by a not-done RU (FEAT link = no member done) — either it shipped without its Gate 1 flip, or its verifications lie |
| L24 | finding | a bound literal that restates a registered `values` entry — reference it instead; `finding` because two numbers can coincide innocently |
| L25 | error | the shall-clause subject names a declared service, and the same one the RU's scope owns. `the system` claims no service and is exempt |
| L26 | finding | a `test`-type verification whose check has been observed green and never red — it has not demonstrated it can fail. Never an error: a check written before its code legitimately has no red, and blocking that rewards theatrical failure (§6.8) |
| L27 | warning | a DRAFT whose segment declaration contradicts its tier, in a store that has adopted segments: a standard draft naming none (Gate 1 would mint it store-wide), or a constitutional draft naming one (a permanent segmented id for a store-wide invariant). Drafts only — a permanent id can never acquire or shed a segment, so the same warning about an active RU would have no available fix |

### Consistency checks (`rqunit check`)

| Code | Severity | What it enforces |
|---|---|---|
| C1 | error / warning | two active RUs on one normalized trigger that CONTRADICT: same obligation with two bounds, or one denying what the other asserts (error); identical responses = duplicate (warning). Sharing a trigger is decomposition, not a smell — a dozen RUs may hang off one endpoint. Semantic contradictions with neither signal are a documented miss |
| C2 | warning | `scope.owns` overlap between RUs of different features with disjoint tags — unrelated domains sharing ownership; aggregated as ONE warning per unordered feature pair (with the RU-pair count), since the feature is Gate 1's attention unit |
| C3 | warning | one RU's `must_not_touch` intersects another's `owns` — the pair can't be co-assigned without H1 blocking the work |
| C4 | error | method+path unique per service (templates normalized: `{id}`≡`{uid}`); WS upgrade paths included |
| C5 | error | endpoint/channel `access` ∈ shared `access_tiers`; endpoint `scope` ∈ `token_scopes` (shared or owning manifest); a shared artifact's `access_tier` ∈ `access_tiers`; an audit or artifact field's `vocab` names an existing vocabulary; a field's `artifact:` names a declared shared artifact |
| C6 | error | every `emits` entry is a declared problem type or audit event |
| C7 | finding | orphan facts: surfaces/shared values referenced by no active RU (statement tokens or model vocabulary) — dead interface or missing requirement either way; during migration this list enumerates legacy-governed surfaces (see §6) |
| C8 | error | every model vocabulary binding resolves to a manifest entry — manifests own vocabulary, models own dynamics |
| C9 | error | message topology: each inbound subject has exactly one in-store outbound declarer with an identical payload type, unless `external: true`; multiple declarers, payload disagreement, and external-with-in-store-declarer are all errors |
| C10 | error | every endpoint declares `inbound` and `outbound` (§5.9). `none` is a declaration; an absent slot is unfinished work; `planned` is no exemption |
| C11 | error | shape well-formedness: presence vocabulary matches the direction (`always\|never` out, `required\|optional\|forbidden` in), inbound resolves an unknown-field policy, `in` is inbound-only, `nullable` is meaningless on a never/forbidden field, arrays name `items`, objects declare members, bound keys suit the type, dotted children imply declared parents |
| C12 | error | path placeholders and `in: path` fields reconcile both ways; placeholder names unique within a path |
| C13 | error | wire-visible names follow the `conventions` declared in the shared manifest (absent table = unenforced) |
| C14 | finding | a state-changing route declares no audit event (constitutional RU-0002 made checkable; the method is a heuristic, so it reports rather than blocks) |
| C15 | error | every shim registration names a model the store carries, once each |
| C16 | error (`warning` for a missing `domain` — nothing reads it) | the segment registry is well formed and every segment an id uses is declared. A segment name is permanent — add and close, never rename or merge — so a name that stops being declared while ids still carry it is unrepairable |

⚠ **Naming collision:** consumers migrating from a pre-existing requirements
system may carry an unrelated legacy control catalog reusing C-numbers. Legacy
catalogs are scoped to legacy-governed areas by the consumer and retire with
the migration; the two numbering spaces are never mixed in one report.

### Conformance divergences (`rqunit conformance`)

Manifest ↔ code, per §5.6/§5.8. A per-stack **extractor** writes what the code
exposes into `actual-surface.json`; the framework owns every judgment about
what a difference means, so a new language costs an extractor, not a
reconciler. The adapter is built in the stack's own build system (the
toolchain never invokes a compiler or build tool); core either reads the
committed artifact or execs the prebuilt adapter as an opaque black box, and
the stack's currency test proves the artifact still matches the code.

| Code | Severity | What it means |
|---|---|---|
| CF1 | error | the manifest declares a surface the code does not serve (`planned: true` exempts it) |
| CF2 | error | the code serves a surface no manifest declares — ungoverned by definition |
| CF3 | error | served, but still marked `planned` — flip it off at Gate 1 (§5.8's other direction) |
| CF4 | error | access tier disagrees between manifest and code composition |
| CF5 | error | a declared outbound message the code never publishes (`external: true` exempts) |
| CF6 | error | the code publishes a message no manifest declares |
| CF7 | error | the route matches but its declared shape and the code's disagree — a field declared and not carried, or carried and not declared. Silent where the adapter reports no shape: omission means *not observed*, never *empty* |
| CF8 | error | two routes serve the same request/response type while their manifests declare different censuses. The code's type is the shape identity the store deliberately does not carry |
| CF9 | error | a covered service declares a surface family no probe examined. `covers` stops an unexamined family reading as an absent one; this stops it reading as a passing one |
| CF10 | error | a declared audit event the code never records. A probe proves the emitting call site EXISTS — not that it runs; dead code and never-taken branches pass, which the proof classes report |
| CF11 | error | an audit code the code records that no manifest declares — evidence with no retention rule and no forbidden-field check |

**Ratified exceptions** live in the store at
`spec/framework/conformance-exceptions.yaml` — `{rule, service, target,
justification}`, the justification mandatory and substantive — and downgrade a
divergence to a reported `finding`. An artifact carrying `exceptions` is
rejected outright: a probe able to author its own waivers could turn its own
mistakes green. They are never silenced: an exception you cannot defend in
prose is a defect wearing a waiver, and one that outlives its reason becomes
camouflage.

### Hooks (agent runtime)

| Code | Behaviour |
|---|---|
| H1 | pre-write: blocks writes matching the armed packet's `must_not_touch` globs, citing the imposing RU; blocks NEGATIVE scope only; inert without `spec/packets/.active` |
| H2 | post-write: appends out-of-`owns` writes to `projections/scope-audit.jsonl`; NEVER blocks (audited residual risk) |
| (unnumbered) | writes into `spec/reviews/` by agents are hook-blocked — Gate 2 records enter only via `rqunit review` (no self-certification) |

### Model dialect checks (M1–M6)

The statechart dialect's beyond-schema graph facts, declared in the schema
that ships with the tool
([model.statechart.schema.yaml](src/rqunit/pack/schemas/model.statechart.schema.yaml))
and enforced as their own lint family — one implementation, two surfaces:
`rqunit lint` reports them, and generation refuses a violating model with the
same messages.

| Code | Severity | Rule |
|---|---|---|
| M1 | error | `initial` names a declared state |
| M2 | error | every transition target is a declared state (a generated test would otherwise assert a transition to nowhere and fail only at shim runtime) |
| M3 | error | final states declare no `on` transitions |
| M4 | warning | at least one final state is reachable from `initial` (graph walk; skipped when M1 already fired — a walk with no lawful start would only cascade the same defect). A warning, not an error: a genuinely cyclic lifecycle legitimately declares no final state, and blocking it would teach people to bypass the gate |
| M6 | error | invariant names are unique within a model (each generates a probe named after it; duplicates collapse check identity) |

Generation refuses on M2, M3 and M6 — the rules the rendered suite depends
on. M1 and M4 are judgments the plan never consults (it reads neither
`initial` nor `type: final`), so they are reported without blocking.

M5 — every event resolves to a manifest entry via the `vocabulary` block — is
deliberately not an M lint: it needs manifests, which makes it C8's
cross-artifact question.

### SCHEMA

`SCHEMA` — reported when an artifact fails its JSON Schema at store load. The
store does not lint a malformed artifact: shape errors must be fixed before
any semantic rule applies.

## 6. Reading debt and burn-down

Standing warnings and findings are the framework's visible-debt mechanism
(spec §6.4/§6.6), not defects: L21 warnings mark under-covered active RUs,
C7 findings mark manifest facts awaiting a governing RU, the untraced-check
list marks tests predating the trace convention. Current figures are never
recorded in documentation — they are read live from the tools:

| Status | Source of truth |
|---|---|
| Lint warnings (L20/L21 burn-down) | `rqunit lint --format text` |
| Orphan facts, untraced checks, unverified RUs | `spec/projections/orphans.md` (regenerated by `rqunit trace`) |
| Suspect links pending Gate 1 | `spec/projections/suspect-queue.json` |
| Per-RU computed status | `spec/projections/ru-index.json` (`computed` field) |
| Area ownership / migration state | the consumer's area ledger (MIGRATION.md, where present) |

Interpretation rule: a rising count is a regression; a falling count is
migration progress. Trends matter; absolute figures do not.
