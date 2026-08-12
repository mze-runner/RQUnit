# Requirement Unit (RU) Framework — Specification Management for Agentic Development

**Status:** v0.16.0
**What changed between revisions:** [CHANGELOG.md](../CHANGELOG.md) — including anything a consumer must do.
**Canonical location:** `spec/framework/ru-framework-spec.md`
**Normativity:** This document is normative for authoring and managing requirements. Where it conflicts with any prose story, epic, or feature description, this document wins. RFC-2119 keywords (MUST, MUST NOT, SHOULD, MAY) apply throughout.

**Scope:** the framework is domain-agnostic and language-agnostic. Examples use an order-management system.

---

## 1. Purpose & Principles

The framework compiles human intent into machine-verifiable requirement units and machine-checkable fact manifests that agents can consume without interpretation, and that humans can audit without re-reading generated output from scratch.

**P1 — Structure is canonical, prose is a projection.** The spec store is the source of truth. Any human-readable narrative (feature overviews, epics) MUST be generated from it, never authored as a parallel source.

**P2 — Every requirement declares how it is proven.** An RU without a verification hook is not a requirement; it is a preference. Preferences are allowed but visible (see `verification: human` debt rule, §6.4).

**P3 — Intent is immutable and traceable.** Every RU points to the source intent artifact it was compiled from. Invention by the analyst is detectable by construction.

**P4 — Definition of done is computed, never asserted.** `done := all(verifications.pass)`. No agent or human marks an RU done by declaration.

**P5 — Append-only with supersession.** Active RUs are never edited in place. Change = new RU + `supersedes` link. Manifest facts follow the analogous discipline: mutations are gated and impact-reported (§5.5), never silent.

**P6 — Context is a query, not a document.** No agent receives "the requirements." Agents receive assembled context scoped to the task (§9).

**P7 — Scope is negative as well as positive.** `must_not_touch` is enforceable and enforced (hooks), not advisory.

**P8 — One fact, one place.** Every fact — an interface surface, a shared value, a vocabulary — is declared exactly once, in a manifest, and referenced everywhere else by id. Restatement is drift waiting to happen; duplication across the spec store is a lint error, not a style issue.

**Doctrine — the clean-room criterion.** The spec store (RUs + manifests + models + their checks) MUST be sufficient for an agent team, given nothing else, to rebuild a system that passes every verification. Equivalence is bounded by the verification set: the rebuilt system is guaranteed to satisfy every declared test, model conformance, and manifest conformance — not to reproduce unchecked characteristics (performance profiles, implementation idioms). Consequence used daily: **any question an implementing agent must ask outside the store is a spec defect** — file it as a GAP. The criterion is seeded as constitutional RU-0003 (§15).

---

## 2. Artifact Types

| Type | Identity | Format | Mutability | Purpose |
|---|---|---|---|---|
| Intent | `INT-<ULID>` | Any (MD, transcript) | Immutable | Raw human input, verbatim |
| Requirement Unit | `RU-XXXX` | YAML | Append-only + supersession | Atomic normative **behaviour** statement |
| Manifest | `<service>.manifest.yaml` | YAML (schema-validated) | Gate-1-gated edits (§5.5) | Interface surfaces + shared **facts**, declared once |
| Model | `MDL-*` | Statechart JSON / decision table | Versioned, content-hashed | Formal **structure/logic** (dynamics) |
| ADR | `ADR-*` | Markdown, `spec/rationale/` (formats §10) | Editable prose — an edit flips every dependent RU suspect (§7.3) | Rationale, decisions |
| Gap | `GAP-XXXX` | YAML | Open → resolved | Analyst-surfaced ambiguity or conflict |
| Feature | `FEAT-*` | YAML | Versioned | Metadata-only grouping + one goal sentence |

The four knowledge classes and their division of labour: **RU = behaviour** (what the system shall do), **Manifest = facts** (what exists: surfaces, their shapes, values, vocabularies), **MDL = dynamics** (when and how states and decisions move), **test = proof**. `actors.yaml` and `tags.yaml` are framework-level manifests — the same declare-once/reference-everywhere pattern applied to the framework's own vocabularies.

### 2.1 FEAT nodes and the fate of user stories / ACs

A traditional user story decomposes as follows: the **"as a / I want / so that" narrative** is intent → lives verbatim in INT; the **motivation** ("so that...") is distilled into the FEAT `goal`; **each acceptance criterion becomes exactly one RU**; every **interface or value fact** the story mentions is declared in a manifest and referenced. There is no story artifact — the story is a projection rendered from FEAT + member RUs.

```yaml
id: FEAT-fraud-screening
goal: >
  Incoming orders are screened by manager-configured fraud rules,
  without requiring manual review of each order.
source_ref: INT-0102#L40-45
status: active
```

FEAT rules:
- FEAT carries NO normative statements, NO verification, NO scope. Grouping + goal only; normative language in a FEAT is a lint error.
- Membership is declared on the RU (`feature: FEAT-...`), never listed on the FEAT.
- FEATs are flat. A FEAT MUST NOT reference another FEAT. Broader groupings are tags.
- Agents MAY receive the FEAT `goal` sentence as framing; they MUST NOT receive "the whole feature" as a work order.

---

## 3. RU Schema

```yaml
id: RU-0204                     # immutable, monotonic, never reused (identity rules: §3.1, §7.1)
statement: >
  The system shall record every screening decision with reason codes,
  retrievable for {value:retention.decision_log_days} days.
syntax: ears                    # ears | gherkin  (enforced by linter, §10.1)
status: active                  # draft | active | superseded | retired
tier: standard                  # standard | constitutional (§3.4)
feature: FEAT-fraud-screening   # optional; grouping only (§2.1)
source_ref: INT-0102#L70-73     # REQUIRED. Intent artifact + location anchor
supersedes: RU-0089             # optional; MUST be set if replacing an active RU
rationale_ref: ADR-0031         # optional but SHOULD be present for non-obvious constraints
verification:                   # REQUIRED, min 1 entry
  - type: test
    ref: "service-orders::retention::decision_records_survive_the_window"
  - type: test
    ref: itest::screening::decision_log_retention
scope:
  owns: [orders/screening]
  must_not_touch: [orders/fulfilment]
tags: [screening, audit]
priority: null                  # FORBIDDEN. Priority lives in TASK nodes only.

# --- tool-written fields (never hand-authored; spec-activate owns them) ---
gate1_stamp:                    # §7.2 — makes "reviewed" computed, not asserted
  hash: "sha256:<canonical hash of statement+scope+verification+tier>"
  by: "<operator id>"
  at: "2026-07-20T09:14:00Z"
link_fingerprints:              # §7.3 — suspect-link detection on every cross-artifact ref
  ADR-0031: "sha256:<content hash at activation>"
  RU-0089:  "sha256:<normative-field hash at activation>"
```

### 3.1 Field rules

- `id` — identity split by lifecycle stage (§7.1): drafts use `RU-draft-<ULID>` (collision-free, no coordination); a permanent sequential id — `RU-<SEQUENCE>` or `RU-<SEGMENT>-<SEQUENCE>`, four base-32 characters (formats §1) — is assigned atomically at Gate 1 from the directory listing. Sequence is monotonic-unique, not gapless; IDs are never reused. Draft cross-references use ULIDs and are rewritten at activation.
- `statement` — exactly one normative statement. Compound statements MUST be split. Quantities MUST be bounded: a bound is either a **literal** ("within 5 seconds") or a **resolvable manifest reference** (`{value:...}`) — never vague (L2). Statements MAY embed manifest references (§5.3); every reference must resolve (L15).
- `syntax` — the statement MUST parse under the declared syntax. EARS templates: ubiquitous, event-driven (`When`), state-driven (`While`), unwanted-behaviour (`If ... then`), optional (`Where`).
- `source_ref` — MUST resolve to an existing immutable INT artifact with a LINE anchor, and the lines must fall inside the file (L4). Section anchors (`#S<slug>`) are retired: an intent is any capture format, so a pasted conversation has no headings to slugify, and the form could only ever be checked for the file existing — an anchor nothing can verify is a preference wearing a syntax. Intent ids are ULIDs: capture has no gate, and the framework allocates a sequence only where creation is already serialized (§7.1), so an id two captures could both pick would be a collision with nothing to serialize it. A store's earlier four-digit `INT-XXXX` ids remain legal permanently — an intent is immutable and every RU compiled from one cites it, so re-identifying it would rewrite reviewed provenance.
- `segment` — DRAFTS ONLY: which id space Gate 1 allocates into (formats §1). Declared by the reviewer, never derived; consumed at activation, because the permanent id then carries it.
- `supersedes` — target transitions to `superseded` automatically at activation. Chains MUST be acyclic.
- `verification` — see §6. At least one entry at all times, including drafts.
- `scope.owns` / `scope.must_not_touch` — repo-relative path globs; the negative scope is hook-enforced. Manifest references are NOT permitted in scope fields — hook enforcement must never depend on reference resolution.

### 3.2 Explicitly excluded fields

No estimation, no priority, no sprint/iteration, no assignee, no workflow states beyond §7. Hierarchy is tags and links; the store is flat. **No `role`/`permission` field**: the role is the EARS actor inside the statement. **No inline interface facts**: an RU that restates a path, subject, frame type, or shared value instead of referencing the manifest violates P8 (L17).

### 3.3 Actors and roles

All actors are declared in `spec/framework/actors.yaml`:

```yaml
actors:
  - id: platform-admin
    description: Administers the platform itself (tenants, global configuration)
  - id: operations-manager
    aliases: [ops-manager, store-manager]   # rejected in statements; lint suggestions only
    description: Configures business rules, channels, and screening policies
  - id: customer-support-agent
    aliases: [support-agent, csr]
    description: Acts on individual orders on behalf of customers
  - id: customer
    description: Authenticated end user placing and managing their own orders
  - id: service-consumer
    description: Downstream system reading order data via API
  - id: system
    description: Internal actor for autonomous behaviour (schedulers, sweepers, pollers)
  - id: anonymous
    description: Unauthenticated principal
```

Rules: the parsed EARS actor of every statement MUST be a canonical registry id (L12); aliases are never valid in statements; new actors enter the registry first; role-variant behaviour = separate RUs per actor (a two-role statement is compound, L3).

**Default-deny root RU (constitutional).** Exactly one ubiquitous root closes the world: *"The system shall deny any action that is not explicitly granted to the requesting actor's role."* (RU-0001, verified by an architecture test over the router composition.) Absence of a grant RU mechanically means denial; per-role denial RUs are written only where the denial itself has observable requirements.

**Permission matrices.** Role×capability grids are decision tables → `model` verification (§6.3), never per-cell RU explosions. A small RU set states the invariants (resolution through the model; default-deny; denial audit); conformance tests are generated per cell. Capability and role identifiers used by the matrix MUST be manifest/registry vocabulary — the model consumes them, it does not define them (§5.7).

### 3.4 Constitutional tier

System-wide invariants carry `tier: constitutional`: included in **every** context assembly; hard-capped at **15 store-wide** (L13); promoted/demoted only at Gate 1; otherwise ordinary RUs — the tier changes distribution, not authority. Seed set: RU-0001 (default-deny), RU-0002 (audit-on-mutation), RU-0003 (clean-room criterion, §1 Doctrine).

---

## 4. Intent Artifacts (INT)

- Captured human intent — brainstorm notes, transcripts, chat exports, and specification documents a consumer already had — stored **verbatim and unedited** under `spec/intent/`, immutable; corrections are new INT artifacts. **Verbatim constrains fidelity, not genre:** a capture asserts that these are its source's words unedited, whether that source was spoken, pasted, or written down long before the store existed. A capture of an existing document carries a provenance header naming the source path and its content hash. No lint checks that words are unedited — L4 resolves the anchor and its line range, nothing more — so this one is the author's to keep.
- INT is **captured, not authored**. Writing a new PRD-style document between intent and RU is forbidden waste. Capturing a document that already exists is a different act: that document is the source.
- Every RU MUST anchor into an INT artifact. Agent-inferred requirements are first written back as a proposal into a new INT the human explicitly acknowledges; the acknowledgment is the source. No RU cites agent reasoning as origin.
- INT is re-read at three expensive moments — supersession, disputes, re-compilation after a pivot. It exists for those, not for daily reading.

---

## 5. Manifests

### 5.1 Purpose

A manifest is the **single source of truth for facts**: everything that exists at a service's boundary or is shared across behaviours — HTTP endpoints, async subjects, WebSocket channels and frames, error/problem registries, audit-event catalogs, cross-cutting values (TTLs, limits, retention windows), and controlled vocabularies. RUs state behaviour *about* these facts and reference them by id; they never restate them.

Manifests serve a second role: they are the **navigation layer for agents**. An implementing agent receives the manifest surface of every service its task touches (§9) — complete interface awareness at a fraction of the context cost of reading code. This only works because manifest↔code conformance is mechanically checked (§5.6): an unchecked map is worse than no map, because agents navigate confidently to interfaces that moved.

### 5.2 Structure

One file per service at `spec/manifests/<service>.manifest.yaml`, validated against the tool's `manifest.schema.yaml` (JSON Schema; CI-blocking). Sections, all optional except identity, at least one interface surface required for boundary services:

- `service`, `version` — identity and manifest schema revision.
- `problem_types` — RFC 7807-style error registry, keyed by short id: `{uri, status, title}`.
- `values` — nested map of cross-cutting scalar facts (TTLs, limits, windows, hash parameters). Leaves are scalars.
- `audit_events` — catalog of `{code, fields, retention?, ru}`. `fields` is a census in the same grammar every other surface uses; the envelope is declared once in `audit_common`, and fields no record may ever carry once in the shared `audit_forbidden` (§5.10).
- `vocabularies` — named controlled value sets (e.g., rate-limit key types), referenced by consistency checks.
- `endpoints` — HTTP surface: `{id, method, path, access, ru, emits[], audits[], publishes[], inbound, outbound, planned?}`. Authoritative for method+path+access and for both directions of the shape (§5.9). The three side-effect keys are separate because they are different claims with different audiences: `emits` is what a CALLER can be told (problem types), `audits` is evidence nobody outside sees, `publishes` is what subscribers receive. One list resolved by trying each registry is ambiguous the day two share a name.
- `defaults` — service-wide defaults overridable at the point of use; currently `unknown_fields` (§5.9). Forbidden in the shared manifest: it shapes surfaces, and the shared manifest carries none.
- `artifacts` — structures minted somewhere, carried as a VALUE inside payloads, and validated elsewhere; shared manifest only (§5.5, §6.1). A field names one with `artifact:`.
- `audit_forbidden` — field names no audit record may ever carry; shared manifest only (§5.10).
- `conventions` — store-wide naming standards for **wire-visible** names (`field_names`, `path_segments`), declared in the shared manifest **only** and enforced by C13. Per-service tables would let a house standard diverge service by service, which is what the table exists to prevent. Spec identifiers are not governed here: the schema fixes those, so every id stays addressable by the token grammar. An absent table means unenforced.
- `messages` — async surface: `{id, subject, direction, payload, ru, audits[], external?, planned?}`. `audits` is inbound-only — on an outbound entry you are producing the message, not handling one — and it closes the largest gap in the old model, where an async consumer that mutated state had nowhere to declare what it recorded. `payload` is a **type name only**, owned by the shared wire-types crate/package — the compiler owns the shape; the manifest never duplicates it. `external: true` marks an inbound subject produced outside the spec store (§5.8).
- `channels` — WebSocket surface: `{id, upgrade_path, access, ru, connection_close_codes[], frames[]}` with frames as `{id, direction, payload}` (type names only).

**A manifest carries facts, never a reference to prose.** A surface has no `story:` or `doc:` key; it reaches its narrative through the requirement that governs it — endpoint → `ru` → `source_ref` → the intent lines the requirement was compiled from.

Every surface entry carries an `ru:` link (the governing RU or FEAT id) — the manifest-side half of bidirectional traceability (§6.6). Conflicts discovered while building a manifest are NEVER recorded as inline comments; they compile to `GAP-` items with `severity: blocking` (§8.1), holding activation of every RU referencing the disputed fact.

### 5.3 Reference syntax

Inside RU statements (and only there — not scope, not verification refs):

```
{value:<dotted.key>}   {endpoint:<id>}   {problem:<id>}   {audit:<code>}
{message:<id>}         {channel:<id>}    {frame:<channel_id>.<frame_id>}
{vocab:<name>}            {artifact:<id>}       {artifact:<id>.<field>}

{endpoint:<id>.<direction>}            {endpoint:<id>.<direction>.<field>}
```

An endpoint reference may address one of the surface's two directions, and a field within that direction's declared census (§5.9); nesting is expressed by the field name (`…outbound.cancellation.at`). `direction` is `inbound` or `outbound` and closed by the grammar — a misspelling is malformed, not unresolved. This is how an RU binds to a shape: the statement names the field, and L15 reports a reference to a field the surface does not declare.

**Cross-service qualifier.** A reference may name the owning service: `{endpoint:service-billing/charge}`, `{problem:service-billing/payment-failed}`. One slash, before the key; grammar in `formats.md` §2. Rules:

- Resolution: a **qualified** reference resolves against the named service's manifest **only** — a miss there is a dangling reference (L15), never a fallback, which would silently bind the statement to a different fact than the one it names. An **unqualified** reference resolves own-scope service manifest → `shared.manifest.yaml`. Shadowing remains forbidden (L16).
- Cross-service references are permitted to **surfaces, problem types, and audit events only — never a foreign service's `values`**. Needing another service's scalar is precisely the §5.5 promotion-to-shared trigger; qualified value refs would bypass that discipline and are an L15 error.
- Referencing is read coupling, not governance: the `ru:` backlink on the surface stays with the **owning** service. A consumer RU referencing a foreign endpoint does not become its governor.
- The §5.5 impact reporter scans store-wide, so mutating a surface lists cross-service dependents — impact reports get more honest, not more expensive.

General rules:
- Every reference MUST resolve (L15). Dangling references fail CI.
- Checks that verify a manifest-referenced bound MUST read the value from the manifest (directly or via generated constants), never hardcode it — otherwise a gated value change passes its impact report while a stale test keeps asserting the old number.

### 5.4 Registration rule (the over-registration guard)

- **Interface surfaces** (endpoints, messages, channels, frames, problem types, audit events) live in the manifest, always — no exceptions.
- **Scalar values** live in the manifest **iff** referenced (or confidently expected to be referenced) by **≥2 RUs**; a single-use bound stays literal in its statement. Rationale: reference indirection has a Gate 1 readability cost — a reviewer fidelity-checking a statement full of symbols reviews nothing. The ≥2 rule pays that cost only where duplication is the greater disease.
- Analyst duty: propose registration when compiling the second RU that would restate a fact. Gate 1 confirms.

### 5.5 Mutation control

A manifest edit is either **additive** (a new entry; changes no existing RU's meaning) or **mutating** (changing or deleting an existing fact; silently changes the effective meaning of every frozen RU referencing it).

**All manifest edits pass Gate 1** — batched into the same sitting as feature activation, so marginal cost approaches zero. Two reasons additive edits are not exempt: under the clean-room doctrine a manifest entry is part of the system's rebuild instructions, and additive is not harmless — a new endpoint is new attack surface, and C7 (orphan facts) converts most additive edits into "write the governing RU anyway."

For **mutating** edits the activation tool additionally generates an **impact report**: every RU and committed packet referencing the changed key, presented to the human at approval; affected RUs' verifications re-run after merge. A mutating manifest edit without an impact report MUST NOT merge.

**Shared manifest** (`spec/manifests/shared.manifest.yaml`) for cross-service facts, governed by three rules:
1. **Promotion by demonstrated reuse** — a fact enters shared only when ≥2 service manifests need it; never speculatively. `artifacts` are the exception: a credential shape has one registry, so it is declared in the shared manifest from the start and a service manifest carries no `artifacts` table (formats §16).
2. **No shadowing** — a service manifest defining a key that exists in shared is a lint error (L16); resolution is always unambiguous.
3. **Widest impact report** — shared edits list affected RUs across all services at Gate 1.

### 5.6 Manifest ↔ code conformance

The manifest is normative; code that disagrees is wrong by definition (spec store is the source of truth — the codebase must be reproducible from it, never the reverse). This is enforced, not asserted:

- **Audit emission is reconciled like any other surface.** A declared audit event the code never records, and a code the code records that no manifest declares, are both divergences. The limit is honest and stated rather than hidden: a route exists in a router table, but an emission is a *call site* — extraction proves the call site exists, never that the line runs. Dead code and never-taken branches pass, so a declared audit event lands in the proof classes above like any other field, and only a test moves it from extractor-confirmed to test-proved.
- **Ratified divergences live in the store**, at `spec/framework/conformance-exceptions.yaml`, and are reported as findings with their justification attached — never silenced. They MUST NOT travel inside an adapter artifact. Everything a probe emits is an *observation* the framework judges; an exception is a *judgment* that overrides it, and the two cannot share a channel once a probe may be written by anyone — a probe able to author its own waivers could turn its own mistakes green. A justification is mandatory and substantive: an exception nobody can defend in prose is a defect wearing a waiver.
- Extraction is per **(language, framework)**: discovering routes in one web framework shares nothing with discovering them in another beyond the parser. An artifact therefore declares which surface families it **examined** — a probe that reads a message library says nothing about routes, and that silence MUST NOT be read as "the code serves none". Artifacts are assembled per service before any judgment, as a union: a surface one probe saw exists whether or not another was looking for it. Judging artifact-by-artifact would make every probe report every other probe's surfaces as undeclared. An artifact that declares no coverage means it examined everything — what a single whole-stack extractor asserts.
- A declared family that no probe examined is a divergence in its own right. Coverage declarations stop an unexamined family reading as an absent one; without this rule they would make it read as a passing one instead, and a run that never asked the question would go green. A service NO adapter reports on stays deliberately out of scope (§5.6 has always said so) — the rule is about a family left unlooked-at within a service some probe did examine.
- Route identity is the path with placeholders reduced to position: `/orders/{id}` and `/orders/:id` are one route spelled by two frameworks, and matching raw strings would report a declared-but-unserved / served-but-undeclared pair for every parameterized route in the store. Placeholder *names* are reconciled separately, by C12, against the `in: path` fields — the only place a name carries meaning. Normalization lives in the core: an adapter that normalized its own paths would be deciding what counts as the same route.
- Each service carries a **generated conformance check** asserting that its runtime surface equals its manifest: the actual router table matches `endpoints` (method, path, access tier, and each direction's declared shape where the adapter can report it — otherwise that field's verification is delegated to the governing RU's tests), subscribed/published subjects match `messages`, and the frame catalog matches `channels`. `planned: true` entries are handled asymmetrically per §5.8.
- A declared field's proof is therefore one of three things, and the report distinguishes them rather than letting one green check stand for all of it: **extractor-confirmed**, **test-proved**, or **unproven**. The manifest is permitted to exceed what an extractor can see — that is what carries target state alongside current state (§5.8 is the same asymmetry at entry granularity) — so the unproven fraction must be reportable, never invisible.
- Manifests are **content-hashed** like models: conformance artifacts record the hash they were generated against; a hash mismatch flips every dependent verification to failing (stale = red, same rule as §6.3).
- Schema validation (`manifest.schema.yaml`) and all consistency checks (§10.2) run on every commit and MUST pass before any gate.

### 5.7 Manifest ↔ model ownership

**Manifests own vocabulary and surface** (what exists); **models own dynamics** (when and how it moves). Where a fact could sit in either, the manifest wins and the model references it:

- Every event, frame, emission, or close code appearing in a model MUST resolve to a manifest entry (C8). A statechart may say *when* `CANCEL` fires; only the manifest says the cancel surface exists and what carries it.
- A model that introduces its own vocabulary is duplicating facts — a P8 violation surfaced by C8, not a modelling choice.

### 5.8 Planned surfaces and external producers

**Planned surfaces.** A designed-but-unbuilt surface carries `planned: true` — NOT a FEAT stub, which would discard the interface facts and leave draft RUs with unresolvable references. Semantics:

- Conformance (§5.6) treats it **asymmetrically**: the entry leaves the expected-equality set — its absence from the runtime surface is expected, not drift — but the actual surface is still matched against planned entries. A runtime surface matching a `planned: true` entry is its own divergence class ("implemented but planned — flip `planned` at Gate 1"), never a silent pass and never a generic undeclared-surface error.
- MUST carry a `ru:` link that is **not done** (L22): an RU link whose computed status is not `done`; a FEAT link qualifies only while **no member RU computes done** (vacuously true for a memberless FEAT — the migration-bridge case). A planned surface governed by a done requirement is a contradiction — one of the two is lying.
- References to planned surfaces resolve normally (L15) — draft and active RUs may cite them; their verifications simply cannot pass until the surface ships.
- Flipping `planned` off is a **mutating** manifest edit (§5.5): Gate 1, impact report. The go-live decision lands exactly where decisions land.
- Under the clean-room criterion, planned surfaces are part of the rebuild instructions; a rebuild produces them planned.

**`planned: true` or a GAP.** Both describe something that does not exist yet, and
the interface facts decide which one to write:

- **`planned: true`** — the interface is decided and the code is not written.
  Method, path, tier and both censuses are known well enough to declare, draft RUs
  can reference them, and conformance expects the surface to be absent.
- **A GAP** — the interface is undecided. A fact a requirement needs is unknown or
  disputed, so there is nothing to declare; `severity: blocking` holds activation
  of every RU that depends on the answer.

For example, a store that must expose a key set for token verification and knows
the route declares `{id: jwks, method: GET, path: /.well-known/jwks.json, access:
public, planned: true}` with a not-done `ru:` link. A store that knows keys must
rotate, but not whether the endpoint serves one key or a set, records a GAP — a
declared census would put a shape nobody has agreed to in front of a requirement.

**External producers.** An inbound subject whose producer lives outside the spec store (e.g., a third-party gateway) carries `external: true`. It is exempt from C9's one-outbound-declarer rule — there is no in-store declarer to find. If an in-store outbound declarer for the subject DOES exist, the `external` marker is itself a C9 error: a wrong marker does not get to disable the check. `external` on an outbound message is a schema error (we always own what we emit). Like the model-vocabulary `internal` escape, `external` markers are reviewed at Gate 1: it is the bucket that will attract exactly the traffic it was built to exclude, and its growth is watched.

### 5.9 Surface shapes

An HTTP surface has two directions, and the manifest declares both. An endpoint carries `inbound` and `outbound`; C10 requires both, at error severity, with no exemption for `planned` — a surface whose shape cannot be stated has not been designed. Shape formats are in `formats.md` §13.

**`none` is a declaration, absence is not.** `inbound: none` and `fields: none` assert that the surface carries nothing in that direction — a positive claim an extractor can falsify. An omitted slot asserts nothing and is unfinished work. Distinguishing the two is the whole reason completeness is mandatory: a boundary that is silent about a direction reads identically to one that has none.

**`inbound` is everything the endpoint accepts** — not only the body. Each field declares `in: path | query | body`. Query strings and path segments are first-class validation surfaces, so a declaration that ignored them would make `inbound: none` false on most reads. Path placeholders are uniquely named within a path and reconciled against the `in: path` fields by C12, so the route template and its constraints cannot drift apart.

**Presence is direction-keyed and the two vocabularies are not interchangeable** (C11). Outbound uses `always | never`, where `never` asserts a field MUST NOT LEAK. Inbound uses `required | optional | forbidden`, where `forbidden` asserts a field MUST BE REJECTED. Optionality is ordinary for input and does not indicate a second artifact type. Where a resource is both read and written the two censuses overlap heavily, and the difference between them is the mass-assignment boundary: the read says `cost_basis: never`, the write says `id: forbidden`. Collapsing them into one shape erases exactly the requirement worth stating.

**Nullability is separate from presence.** Presence is about the key; `nullable` is about the value. An object that is never absent but may be null is a different contract from one that is sometimes absent, and `presence: always, nullable: false` is a claim the store could not otherwise make.

**Bounds reference `values`; they do not restate them.** `max_chars: "{value:email.max_chars}"` keeps one source for a registered fact; a literal duplicating a registered value is an L24 finding. The bound-key set is closed — lengths, numeric ranges, item counts, vocabulary membership — with no expressions, no operators, and no regex. This is the assertion-DSL line, and it is drawn deliberately.

**`outbound` declares the success response and its status.** Problem responses are not declared here: they are owned by `emits` → `problem_types`. The two registries cannot collide: a success status is 2xx–3xx and a problem status is 4xx–5xx, so the schema makes the overlap unrepresentable and no rule is needed to forbid it. One status per endpoint — the known multi-status cases return the same body under a different code, and are served additively when a real case arrives rather than by duplicating a census.

`messages` and `channels.frames` continue to carry a type name rather than a census. Bringing them onto the same shape grammar is additive and follows.

### 5.10 Audit records are evidence

An audit event is an interface surface (§5.4) and always has been. What it was missing was everything that makes it *evidence* rather than a log line.

**It carries a census, in the same grammar as every other surface** — presence, type, vocabulary, nesting. Presence is the OUTBOUND vocabulary (`always | never`): a record is minted, never accepted, so `forbidden` is the wrong claim to make about one, and C11 says so.

**`retention` is declared on the event**, not restated in every RU that mentions it. The fact has one home, so a single constitutional RU can require it of every record.

**`audit_forbidden` is store-wide.** Credential material in an evidence trail is the audit equivalent of a mass-assignment hole, and it is not an event-by-event judgment — declaring it once in the shared manifest makes an omission visible instead of a per-event oversight. An audit census declaring a forbidden field as `always` is a C6 error.

**`level` is retired.** Trace/debug/info/warn/error is *logging severity* — the vocabulary of the thing audit is not. A record either happened and must be kept, or it did not.

**Emission is reconciled** (§5.6): a declared event the code never records, and a recorded code no manifest declares, are both divergences. Observability proper — metrics, spans, ordinary logs — is deliberately not modelled: a metric is not a boundary anyone contracts on.

---

## 6. Verification Types

### 6.1 Shape binding (the retired `contract` type)

There is no `contract` verification type. A shape is a manifest fact — an endpoint's `inbound`/`outbound` census, an audit event's field list, a shared `artifacts` entry — and an RU binds to one by **addressing it in the statement** (`{endpoint:get_order.outbound.cost_basis}`, `{artifact:jwt-access-token.iss}`), then proving it with a `test`.

A manifest already *is* a contract: it has callers, subscribers and error handlers, so an RU binds to a shape by addressing it in the statement and there is no second mechanism for the same relationship. One case a census cannot reach is structure behind an **encoding boundary** — a response declares `access_token: string`, and the claims live inside that string. Those are `artifacts` in the shared manifest (§5.5), referenced from a field by `artifact:` and addressable as `{artifact:<id>[.<field>]}`.

The coverage policy can still require shape binding: `binds_shape` (§6.7) reads the statement, so "a security RU must be bound to a declared shape" survives the change rather than degrading to "must have two mechanical checks".

### 6.2 `test`
References an executable test by stable identifier; CI resolves refs and fails on dangling ones. Tests asserting manifest-referenced bounds read them from the manifest (§5.3).

### 6.3 `model`
References a formal model (`MDL-`) from which conformance checks are **generated**, never hand-written.

```yaml
verification:
  - type: model
    ref: MDL-order-lifecycle
    model_hash: "sha256:9f1c…"      # REQUIRED. Content hash at generation time
    conformance: generated          # generated | manual (manual requires justification)
```

**Shim registration (MANDATORY for depth).** A generated suite drives a hand-owned **shim** the APPLICATION provides. Until the store records that shim in `spec/framework/shims.yaml` — a human claim, checked by C15 — the suite is rendered unrunnable (ignored-with-reason), contributes **zero** depth to the coverage policy (§6.7, L21) — the mechanical minimum and the type clauses alike — and is reported apart from suites that execute. A suite that cannot execute is not depth: this is the last place declared depth could exceed provable depth.

**Anti-drift rule (MANDATORY):** CI recomputes the hash every run; a mismatch makes the verification **stale** and the RU *failing* until conformance is regenerated. Green against a stale hash is red. The same hash discipline applies to manifests (§5.6).

**Model evolution:** editing a referenced model is lawful through **re-affirmation** — a Gate 1 act (`reaffirm`, reviewer-gated) that updates each active dependent's `model_hash` to the current model, re-stamps under the reviewer's id, and regenerates conformance. The reviewer's judgment is the gate: an RU whose *meaning* the model change alters is superseded instead of re-affirmed. Superseded and retired RUs keep their historical hashes untouched — provenance, never a currency claim — and re-stamping moves `gate1_stamp.at`, so prior Gate 2 records for re-affirmed RUs stop counting (the thing they judged was verified against a different model). Hand-editing a hash without the ceremony remains an L19 error.

**Applicability test:** every node/transition must have exactly one executable meaning with no prose annotation. If a node needs a paragraph, it is a drawing — use `test` + statement instead. Model classes: decision graphs/tables (*diagram-as-source*: executed directly, zero drift possible), statecharts (*diagram-as-oracle*: code hand-owned, tests generated), dataflow topologies (wiring + property checks generated). All model vocabulary resolves to manifests (§5.7).

**Statechart dialect (M1–M6).** Graph facts a JSON Schema cannot express, enforced as their own lint family — one implementation, two surfaces: reported at `lint`, and generation refuses a model whose violation would make the rendered suite wrong.

| Code | Severity | Rule | Why |
|---|---|---|---|
| M1 | error | `initial` names a declared state | the machine must start somewhere real |
| M2 | error | every transition target is a declared state | a generated test would otherwise assert a transition to nowhere and fail only at shim runtime |
| M3 | error | final states declare no `on` | a state cannot be both an end and a waypoint |
| M4 | warning | at least one final state is reachable from `initial` | a machine that cannot finish models a process nobody completes — but a genuinely cyclic lifecycle legitimately declares no final state, so this is visible debt, never a block |
| M5 | error | every event resolves to a manifest entry via `vocabulary` | delivered as C8: it needs manifests, which makes it cross-artifact |
| M6 | error | invariant names are unique within a model | each generates a probe named after it, and duplicates collapse check identity |

M4 is skipped when M1 already fired: a reachability walk with no lawful start would report one defect under two numbers. Generation refuses on M2, M3 and M6 — the rules the plan's rendering actually depends on; M1 and M4 are judgments the plan never consults, so they are reported without blocking.

### 6.4 `human`
Explicitly deferred judgment. Allowed, but: human-only verification is a standing lint warning (visible debt); surfaced as Gate 2 review items with recorded pass/fail + note; agent self-certification FORBIDDEN. Store-wide metric `% human-only` reviewed monthly — a rising trend means the framework is degrading into prose with extra steps.

### 6.5 Missing checks
Implied-but-absent checks get `ref: TODO(<description>)`, which auto-generates a work item. A TODO'd RU may be `active` but computes *blocked*, never *pass*.

**Resolving a TODO:** once the check exists, conversion is a Gate 1 act, not a supersession — `resolve` replaces the TODO entry with a real, resolvable ref (a scanned test id) and re-stamps under the reviewer's id. The path is strictly strengthening: statement/scope/tier untouched, entries never removed, real refs never replaced — anything else remains supersession-only. Multiple TODOs must be disambiguated by description substring, and indistinguishable duplicates refuse outright (an authoring bug, cleaned by supersession). Re-stamping moves `gate1_stamp.at`, so prior Gate 2 records stop counting; hand-editing a ref without the ceremony is an L19 error.

### 6.6 Bidirectional traceability

Every test declares which RU(s) it verifies (`verifies(RU-XXXX)` annotation, or inherited from a model's RU links for generated suites); every manifest surface entry carries its `ru:` link. CI computes the orphan reports:

- **Unverified RUs** — covered by computed status.
- **Untraced checks** — behaviour no requirement governs: compile the missing RU (via new INT acknowledgment), delete the check and its behaviour, or mark `trace: infrastructure` (audited — a growing infrastructure bucket is the escape hatch rotting).
- **Orphan manifest facts** (C7) — a surface or shared value no active RU references: dead interface or missing requirement; a finding either way.

**Adoption is reversible.** A trace annotation lives in the consumer's own source because the framework asked for it, so the framework MUST be able to take it back: `rqunit trace --strip` removes annotations naming no active RU, and `--all` removes every annotation including the `infrastructure` markers. The judgment is core's — which tokens are stale is a store question, and an adapter is never asked it — while the rewriting is the **stripper** role's, because only a stack knows what its own annotation looks like. A partially-stale annotation keeps its live tokens: a check proving three RUs, one retired, keeps the other two. Nothing is written without an explicit apply, a stripper answer naming a check core did not ask about is refused rather than written, and a stack declaring no stripper is REPORTED as un-strippable rather than reported clean — a stack that can be adopted but not un-adopted is a one-way door, and the operator has to see it. Artifact transport cannot serve this role: the answer depends on a request computed from today's store, so a committed file would be an earlier run's edits applied to current source.

L14 blocks new untraced checks; pre-existing ones burn down. "New" is set difference — the check ids the scanner observes at head minus those it observed at the base ref — never diff-line inspection, which would put language knowledge in the framework. The base observation is governed by the base tree's own configuration: widening a scan makes previously unobserved checks new, deliberately, because a check nothing had ever observed has never been judged; a renamed untraced check is one deletion plus one addition, and the addition still blocks. A requirement without behaviour, a behaviour without a requirement, and a fact without a governor are all equally detectable.

### 6.7 Coverage policies — verification depth by criticality

"At least one verification" is a floor, not a policy: a constitutional security invariant and a cosmetic tooltip clearing the same bar is a defect. Verification **depth** is declared as data in `spec/framework/coverage.policy.yaml` and enforced by lint (L21):

```yaml
# First matching rule wins; `default` closes the set. Policy is data — extending
# it is a PR to this file, never a lint code change.
rules:
  - match: { tier: constitutional }
    require: { min_mechanical: 2 }            # ≥2 of test|model
  - match: { tags_any: [safety, authz] }
    require: { types_all: [test], binds_shape: true }   # proved AND bound
  - match: { tags_any: [audit] }
    require: { binds_shape: true }
default:
  require: { min_verifications: 1 }
```

Rules:
- `mechanical` = test | model; `human` never satisfies a mechanical minimum. `binds_shape` reads the STATEMENT, not `verification`: it is satisfied by a token addressing a declared census or artifact, and a bare `{endpoint:<id>}` does not satisfy it — naming a surface is not describing what it carries.
- Policy violations are blocking at activation (a draft cannot activate under-covered) and warnings on already-active RUs after a policy tightening — tightening generates a burn-down list, never a mass red build.
- The policy file itself is Gate-1-governed (it changes what "adequately verified" means store-wide — that is a human decision with an impact report, same discipline as a shared-manifest edit).

### 6.8 Check evidence — whether a check discriminates

Depth counts checks. It cannot tell whether a check *distinguishes* anything. An agent that has read the implementation and then writes a test asserting that implementation's shape produces a check that is green on its first run, stays green through every change preserving the shape, and is indistinguishable at rest from a check that earns its green. Coverage rises; nothing is proved.

What separates them is history. A check that has **ever** been observed failing has demonstrated it can fail; one that has only ever been green has demonstrated nothing. So the framework keeps an append-only ledger of firsts at `spec/check-evidence/check-evidence.jsonl`: one line per check per *first* pass and *first* failure.

> **Vocabulary.** This is the framework's evidence about its own checks. It is not the AUDIT record — the consumer system's evidence to its operators (§5.10). The two never share a file, a key, or a rule.

A per-stack **evidence probe** reads its runner's output and reports which checks passed and which failed (contract: `interfaces/check-evidence.schema.json`); `rqunit evidence record` folds a run into the ledger. The split is the adapter rule applied unchanged: a probe reports outcomes, and deciding that an outcome is a *first* requires history, which is a judgment. Probes emit no timestamps — their output must be a byte-deterministic function of their input, so the recording time is core's to stamp.

Only firsts are recorded. A second red proves nothing a first red did not, and recording it would make an append-only file grow with every CI run while saying the same thing.

**L26** reports a `test`-type verification whose check has been observed green and never red. It is `finding`-class and must never be promoted to `error`: a check may legitimately never have been observed failing — it was written before the code, and the ledger only begins when recording begins — and blocking that case rewards theatrical failure (break it once, record the red, restore it). A check with no evidence at all is never reported: absence of evidence is not evidence of absence. The rule is scoped to `test` refs, because a `model` suite is generated from the statechart and cannot be shaped by the implementation it checks.

---

## 7. Lifecycle

```
draft ──(activation gate, §8.2)──▶ active ──(superseded by new RU)──▶ superseded
                                     │
                                     └──(explicit retirement, human-approved)──▶ retired
```

`draft` — analyst output, invisible to assembly. `active` — normative. `superseded` — retained forever; chains answer "why does this constraint exist." `retired` — intent withdrawn, human-approved with reason. In-place edits to active RUs are FORBIDDEN except tags and typo-class fixes to non-normative fields; `statement`, `scope`, `verification` freeze at activation. (Note the interaction with §5.5: a frozen statement's *reference* is stable; the referenced *fact* changes only through a gated, impact-reported manifest edit.)

### 7.1 Identity assignment

Permanent IDs are assigned at Gate 1 — the one already-serialized point — by the activation tool in a single commit: list `spec/ru/`, take max **within the target segment**, bump; rename `RU-draft-<ULID>.yaml` → the permanent filename (ULID kept as `draft_id`); rewrite draft cross-references; set `active` and flip any `supersedes` target. Parallel drafting never contends on IDs; splitting the rename and reference-rewrite across commits is FORBIDDEN (it creates a window of dangling ULIDs).

The **segment** a draft is allocated into is declared on the draft (`segment`, formats §1) and consumed by activation — once the id carries it, a second copy of the same fact could disagree with the id. It is never derived from `scope.owns`: segments and services are many-to-many, so derivation would silently impose the physical axis and be wrong on a monolith hosting several domains and on a domain spanning several services alike. A draft that declares no segment is allocated into the unsegmented space, where a requirement governing the whole store belongs.

Activation refuses to allocate into a segment the store does not declare, or into one declared `closed` — a segment name is permanent once its first id is minted (§10.2, C16), so it is registered before the sitting rather than invented by it. Each segment is an independent sequence: the ceiling is per space, and the nearest answer to exhausting one is usually another segment rather than a width migration.

**Reading the listing is what makes allocation safe.** `max + 1` over what exists cannot mint an id that already exists; a `NEXT_ID` counter file is FORBIDDEN because it races across branches. This is also why a store must be read in ONE base: decimal-spelled ids are legal base-32 ids whose reinterpretation preserves order, so a store that started decimal continues in base-32 with nothing rewritten — but a store read as decimal in one place and base-32 in another has two allocators disagreeing about what is taken.

### 7.2 Gate stamps — reviewed is computed

P4 applies to review status too: "reviewed" MUST be a computed fact, not a checkbox. At activation, `spec-activate` writes a **gate stamp** into the RU: a hash over the canonical serialization of the normative fields (`statement`, `scope`, `verification`, `tier` — canonical form defined in `formats.md`) plus reviewer id and timestamp.

- L19 recomputes the stamp continuously: **a hash mismatch on an active RU means its normative fields changed after review** — either forbidden in-place editing or tool error; both are blocking. The §7 freeze is thereby a mechanical check, not a convention.
- Gate 2 verdicts are **append-only record files** under `spec/reviews/RU-XXXX/` (`{verdict, criterion, note, reviewer, at, packet}` — format in `formats.md`). An agent cannot write a passing record for its own work (H-class hook denies review-path writes from implementation tasks).
- Computed: `ru.reviewed := valid gate1_stamp ∧ every human-type verification entry has a passing Gate 2 record dated after the stamp`. A normative change (via supersession) resets the clock — old Gate 2 records never carry over to the successor RU.

### 7.3 Suspect links — every cross-artifact edge is fingerprinted

Models and manifests are hash-guarded, and so is every cross-artifact edge. At activation, the tool records a **fingerprint for every cross-artifact reference** the RU carries — `rationale_ref` ADRs (file content hash) and `supersedes`/related RU links (normative-field hash) — in the tool-owned `link_fingerprints` map.

- L20 recomputes fingerprints continuously. A mismatch marks the link **suspect**: the target changed after this RU relied on it. Suspect ≠ failing — the RU's checks may still pass — but the RU surfaces in the **suspect queue** presented at the next Gate 1 sitting.
- Resolution is binary: **re-affirm** (human confirms the changed target still supports the RU; tool refreshes the fingerprint under the reviewer's id) or **supersede** (the change invalidated the RU's rationale; compile a successor).
- Packets already snapshot resolved content and hashes (§9.1), so committed packets are never retroactively suspect — the mechanism governs the *live* store only.
- Consequence worth stating: an ADR is not freely editable prose. Rewriting one flips every dependent RU suspect, which is correct — the rationale those RUs were reviewed against is gone.

---

## 8. Roles & Gates

### 8.1 Analyst agent contract

**Input:** INT artifacts. **Output:** draft RUs, draft manifest entries/edits, a gap list — nothing else.

1. Compile only what is unambiguous. Unstated bounds, actors, triggers, or responses become `GAP-` items with `severity: blocking | clarify-later`; blocking gaps hold activation of affected RUs. Never default an ambiguity.
2. Zero gaps from a substantial INT artifact is a red flag, flagged for closer review — it signals guessing, not completeness.
3. Fabricating any `test`/`model` ref is FORBIDDEN — use TODO refs.
4. The analyst MUST NOT modify code or models. RUs, manifest drafts, gaps, TODO work items only.
5. Dedupe duty: before emitting drafts, query `ru-index.json` for matching normalized triggers or overlapping scope; list candidate duplicates alongside drafts.
6. Registration duty (§5.4): on compiling the second RU that would restate a fact, propose a manifest entry and rewrite both statements to reference it. Conflicting facts across sources compile to blocking GAPs, never to silently chosen winners or inline comments.

### 8.2 Human gates (two, distinct, never conflated)

**Gate 1 — Translation fidelity (at activation).** *"Is this a faithful compilation of the thing I said?"* Reviewed per **feature batch** against `source_ref` — the analyst presents a compilation table (INT excerpts beside draft RUs), the gap list, duplicate candidates, and any **manifest edits with their impact reports** (§5.5); the human approves or amends the set in one sitting. Per-RU review at scale (~40h per ~1,500 RUs) rots into rubber-stamping; feature-batch review preserves honest checking at ~10× throughput while keeping activation serialized.

**Gate 2 — Goal verification (at task completion).** Applies only to `human` verification entries: *"does the built thing achieve the intent?"* Recorded per entry.

Conflating the gates produces the failure mode where the spec was approved and all tests passed, yet the software misses the point — everyone verified something, nobody verified the thing that mattered.

### 8.3 Implementing agents

Receive assembled context (§9), never the store. MUST NOT create, edit, or retire RUs or manifests — ambiguity mid-task halts the thread and emits a GAP. `must_not_touch` violations are blocked by pre-write hooks, not convention. Under the clean-room doctrine, any question an implementer must answer from outside the store is itself a GAP to file.

---

## 9. Context Assembly

For a task referencing RU IDs `{R}`:

0. All `tier: constitutional` RUs, always, first.
1. Every RU in `{R}` (statement + scope + verification refs) with **manifest references resolved inline**, plus each RU's FEAT `goal` sentence.
2. **Manifest star map**: the manifest entries referenced by in-scope RUs, plus a one-screen surface summary (endpoint table, subjects, channels) of every service the task's scope touches — complete interface awareness without reading code.
3. Linked `rationale_ref` ADRs; linked models; the censuses the task's surfaces declare.
4. RUs one hop out via supersession-siblings and shared `scope.owns` overlap, read-only, **capped at k=8**, ranked by shared feature then tags; beyond the cap, IDs only.
5. Never: drafts, retired RUs, whole features as work orders, unrelated tag groups, the full store.

The assembler answers queries; it never orchestrates.

### 9.1 Materialized task packets

Every assembly is written to `spec/packets/TASK-XXXX.packet.md`, committed with the work:

- The packet is the complete and exact store-derived context the agent received; nothing bypasses it.
- Manifest references are recorded **resolved** — the actual values and surface entries the agent saw — together with the **manifest and model hashes** at assembly time. The flight recorder is therefore immune to later manifest edits: "why did the agent do that?" is answered by the packet, deterministically.
- Packet generation is a pure function of `(task refs, store state, mode)`; byte-identical modulo a generated-at header, regression-testable.
- Hand-editing FORBIDDEN; immutable once the task completes; re-runs produce new versions.
- A packet declares its **mode**, recorded in the header. `implementation` is the default. `check-authoring` appends one section: write the checks from the statements, do not read the files the task owns, run them expecting red, and record that run (§6.8). An agent authoring checks with the implementation in context writes assertions shaped by it — not disobedience, salience — and instructions do not counteract salience. So the framework states the discipline and does not pretend to enforce it: no hook gates reads, any out-of-band retrieval would defeat one, and a guardrail that reads as a guarantee is worse than a stated rule. What makes the discipline checkable is evidence, not policing — a check authored before its implementation is observed red first, and one that was only ever green is reported by L26 whatever the packet instructed.

---

## 10. Enforcement Layer

This section is the framework. Without it, the rest of this document is prose.

### 10.1 Lints (CI, blocking)
- L1: `statement` parses under declared `syntax`.
- L2: bounds are literal or resolvable `{value:...}` refs; unbounded quantifiers ("quickly", "soon", "many") → error. Scans authored prose only — reference-token spans are excluded (a manifest identifier like `{problem:too-many-requests}` is not chosen words); bare, un-braced identifiers still scan.
- L3: compound-statement detection → error.
- L4: `source_ref` resolves to existing INT with valid anchor.
- L5: `verification` non-empty; all non-TODO refs resolve (`model` → spec/models/; `test` resolution is `rqunit trace`'s).
- L6: `model_hash` / manifest hash current (staleness → dependent RUs failing). Active and draft RUs only — superseded/retired hashes are provenance (§6.3 model evolution).
- L7: cross-artifact link integrity — supersession chains acyclic; superseded targets not retired; `supersedes` and `rationale_ref` targets exist.
- L8: forbidden fields absent (priority, estimate, assignee, role/permission).
- L9: id format matches lifecycle stage; filename matches id; no active RU references a draft ULID.
- L10: tags ∈ `tags.yaml` controlled vocabulary.
- L11: FEAT nodes contain no normative language, no verification/scope.
- L12: parsed EARS actor ∈ `actors.yaml`; aliases rejected with rename suggestion.
- L13: constitutional RUs ≤ 15 store-wide.
- L14: every non-infrastructure check carries a resolvable `verifies(RU-XXXX)` trace; generated suites inherit from model links.
- L15: every manifest reference in a statement resolves — qualified refs against the named manifest only (no fallback), unqualified refs own-scope then shared (§5.3). Qualified references to a foreign service's `values` are errors regardless of resolvability.
- L16: no shadowing — a service manifest key duplicating a shared key → error.
- L17: fact restatement — a statement containing a literal path, subject, payload type, or a value that exists in a reachable manifest → error with the reference suggestion (P8 enforcement).
- L18: manifest files validate against `manifest.schema.yaml`; every surface entry carries a resolvable `ru:` link.
- L19: every active RU carries a `gate1_stamp` whose hash matches the current canonical serialization of its normative fields (§7.2); mismatch = post-review mutation → blocking.
- L20: every `link_fingerprints` entry matches the current fingerprint of its target (§7.3); mismatch → link suspect, RU enters the suspect queue (finding-class, surfaced at Gate 1, not a red build).
- L21: every RU satisfies the first matching rule in `coverage.policy.yaml` (§6.7); blocking at activation, warning + burn-down for actives after policy tightening.
- L22: every `planned: true` surface entry's `ru:` link is not-done — for an RU link, computed status ≠ done; for a FEAT link, no member RU computes done (§5.8). Violation → blocking: either the surface shipped without its Gate 1 flip, or verifications pass against a surface that supposedly does not exist.
- L25: the shall-clause subject resolves to a declared service manifest, and agrees with the service the RU's `scope` owns. `the system` claims no service and is exempt, which is what keeps store-wide and service-scoped behaviour distinguishable. Two claims about which service governs an RU — the subject and `scope.owns` — must agree, or the RU is filed against a service it does not govern. §5.3: referencing is read coupling, not governance.
- L26: a `test`-type verification whose check has been observed green and never red → finding. A check that has never failed has not demonstrated it can; never promoted to error, because a check written before its code legitimately has no red, and blocking that rewards theatrical failure (§6.8).
- L27: a draft whose segment declaration contradicts its tier, in a store that has declared any segment → warning. The absence of a segment is a positive claim — this requirement governs the store rather than a domain — and the schema already makes that population the constitutional tier, which alone may omit `scope.owns`. So a standard draft naming no segment would be minted store-wide, and a constitutional draft naming one would mint a permanent segmented id for a store-wide invariant: a segment holding cross-cutting concerns is the unsegmented space under a nicer name. Scoped to DRAFTS because a permanent id can never acquire or shed a segment: the same warning about an active RU would be advice with no available fix, which is how a rule teaches consumers to ignore the tool. Silent in a store that has adopted no segments — a rule firing on a shape nobody opted into demands adoption rather than enforcing a decision (formats §1).
- M1–M4, M6 (statechart dialect, §6.3): `initial` ∈ states; every transition target ∈ states; final states carry no `on`; at least one final state is reachable from `initial` (warning, and skipped when M1 fired — a walk with no lawful start would cascade one defect under two numbers); invariant names unique per model. One implementation, two surfaces: reported at lint, and generation refuses on M2/M3/M6 with the same messages. M5 (every event resolves to a manifest entry via `vocabulary`) is C8's cross-artifact question.

### 10.2 Consistency checks (CI, blocking)
- C1: two active RUs on the same normalized trigger (actor–verb–object) that CONTRADICT each other → error; identical responses → duplicate warning. Sharing a trigger is not itself a conflict — §2.1 makes each acceptance criterion exactly one RU, so a dozen RUs may hang off one endpoint, and that is what a well-decomposed feature looks like. Two contradictions are mechanically visible: the same obligation carrying two different bounds, and one response asserting what another denies. A semantic contradiction with neither signal ("shall retry" against "shall abandon") is NOT caught, which extends the paraphrase miss this check already documents — analyst dedupe (§8.1) mitigates; supersession repairs the rest.
- C2: overlapping `scope.owns` across unrelated domains → warning at Gate 1.
- C3: `must_not_touch` intersecting a co-assigned RU's `owns` → warning.
- C4: method+path uniqueness per service, upgrade paths included → error.
- C5: vocabulary membership — every constrained field value (e.g., a limit-type on an audit event) ∈ its declared `vocabularies` set → error. Endpoint `scope` ∈ `token_scopes` (shared or owning manifest); a shared artifact's `access_tier` ∈ `access_tiers`; an audit or artifact field's `vocab` names an existing manifest vocabulary; a field's `artifact:` names a declared shared artifact.
- C6: `emits` entries resolve to declared `problem_types` / `audit_events` → error.
- C7: orphan manifest facts — surfaces or shared values referenced by no active RU → report (dead interface or missing requirement; a finding either way).
- C8: every model event, frame, emission, or close code resolves to a manifest entry → error (manifests own vocabulary; models own dynamics).
- C9: message topology — every inbound message subject matches **exactly one** outbound declaration store-wide with an identical `payload` type, unless the inbound entry carries `external: true` (§5.8). Zero declarers (non-external) or multiple declarers → error; payload-type disagreement between the declarer and any consumer → error; an `external: true` inbound whose subject HAS an in-store outbound declarer → error (the marker is wrong, and it is silently exempting the pair from payload agreement). Planned entries participate (topology is designed before it ships).
- C10: every endpoint declares both `inbound` and `outbound` (§5.9) → error. `none` is a legal declaration; an omitted slot is not, and `planned` is no exemption. Enforced as a rule rather than a schema requirement so a shortfall is one attributable violation per endpoint, not a parse failure.
- C11: declared shapes are well-formed → error, across every census a manifest carries: an endpoint's two directions, an audit record's field list, and a shared artifact's. Presence vocabulary matches the slot's direction (`always|never` outbound, `required|optional|forbidden` inbound) — audit records and credentials are minted rather than accepted, so both take the outbound set; an inbound shape resolves an unknown-field policy; `in` is inbound-only; `where` (claims vs header) is artifact-only, because on a payload the position is the field name; `nullable` is meaningless on a field that never appears; `type: array` names its `items`; `type: object` declares at least one member; bound keys suit the declared type; a dotted child implies a declared parent, and a `never`/`forbidden` parent carries no children.
- C12: path placeholders and `in: path` fields reconcile in both directions, and placeholder names are unique within a path → error.
- C13: wire-visible names follow the `conventions` declared in the shared manifest → error where a convention is declared; absent table means unenforced.
- C14: a state-changing route declaring no audit event → finding. The audit-on-mutation invariant made checkable; the HTTP method is a heuristic rather than proof, so it reports rather than blocks. The finding states the invariant and names no RU id — a store seeds its own constitutional set (§3.4).
- C15: every shim registration names a model the store carries, once each → error. A registration is a depth claim (§6.3): one naming a model the store does not carry proves nothing, and a duplicate makes "is this registered" ambiguous the moment two entries disagree about who registered it and when.
- C16: the segment registry is well formed, and every segment an id uses is declared → error, except a missing `domain`, which is a warning: nothing reads it, `domain: TBD` satisfies everything a machine can check of it, and a red build for a sentence of prose teaches consumers to bypass the gate. Segments partition ALLOCATION, never verification — every rule stays store-wide (§1). A segment name is the one vocabulary in this store that is PERMANENT: it lives in filenames, gate stamps, Gate 2 review directory names, packets and `verifies:` annotations in consumer source, and ids are never rewritten, so a rename or a removal is a mass supersession rather than an edit. Retirement is `closed: true`, which keeps existing ids working.
- C17: every access tier a declared surface uses is bound to the credential that admits it → error. Exactly one artifact carries that `access_tier`, or the tier is listed in `credential_free_tiers` (shared manifest). The tier string is the join and the binding is derived: an endpoint declares its tier and never an artifact, so `access` and the credential cannot disagree. One tier admits one credential shape; two accepted shapes are two tiers. Scoped to tiers a surface actually uses, so a vocabulary may run ahead of the surfaces that will use it (§5.9, formats §16).

### 10.3 Hooks (runtime, blocking)
- H1 (pre-write): writes matching in-context `must_not_touch` globs → blocked.
- H2 (post-write): writes outside the union of in-context `owns` globs → flagged for audit (accepted residual risk).

### 10.4 Computed status
```
ru.done      := all(v.pass) ∧ no TODO refs
ru.blocked   := any TODO ref
ru.failing   := any v.fail ∨ any stale model/manifest hash ∨ invalid gate1_stamp
ru.debt      := verifications == [human]
ru.reviewed  := valid gate1_stamp ∧ all human entries have passing Gate 2
                records dated after the stamp
ru.suspect   := any link_fingerprints mismatch      (orthogonal flag: a done
                RU can be suspect — checks pass, rationale moved underneath)
```
Dashboards render computed status only. No manual status field exists — including for review state.

---

## 11. Projections (Human-Readable and Machine Index)

- `spec/projections/ru-index.json` — generated: `{id, status, tier, tags, scope, verification_types, manifest_refs}` per RU. Search hits the index, never the directory.
- Feature overviews generated from the graph; manifests project per-service **surface sheets** (the human-readable star map).
- Projections carry a generated-at stamp; hand-editing FORBIDDEN; regeneration overwrites. Narrative lives in ADRs and INT, which projections may quote.

---

## 12. Storage & File Structure

### 12.1 Layout

```
spec/
  framework/pack.yaml                  # SPEC version this store was authored against
  framework/coverage.policy.yaml       # verification-depth policy (L21, §6.7)
  framework/conformance-exceptions.yaml # ratified divergences (§5.6; formats §14)
  framework/shims.yaml                 # registered statechart shims (§6.3, C15)
  framework/segments.yaml              # declared id segments (formats §1, C16)
  framework/tags.yaml                  # controlled tag vocabulary (L10)
  framework/actors.yaml                # controlled actor registry (L12)
  intent/INT-<ULID>.*                  # immutable, verbatim
  ru/RU-<id>.yaml                      # ONE FILE PER RU (§12.2)
  features/FEAT-*.yaml                 # one file per FEAT
  manifests/<service>.manifest.yaml    # one manifest per service
  manifests/shared.manifest.yaml       # cross-service facts (§5.5)
  models/MDL-*.json                    # formal models, one file per model
  gaps/GAP-XXXX.yaml                   # open ambiguities & conflicts
  rationale/ADR-<slug>.md              # decision records behind rationale_ref (§7.3; formats §10)
  reviews/RU-XXXX/*.yaml               # append-only Gate 2 records (§7.2)
  check-evidence/check-evidence.jsonl  # append-only ledger of check firsts (§6.8)
  packets/TASK-XXXX.packet.md          # materialized assembly, immutable post-task
  projections/                         # generated only
```

The JSON Schemas the store validates against are NOT store content: they ship
inside the tool, so a store is always checked by the schemas of the version
enforcing it. `framework/` holds only what the consumer authors or tunes —
vocabularies, the coverage policy, and the pack pin (formats §8).

### 12.2 Granularity rule: one RU, one file (normative)

The store is NEVER a single document. Reasoning, in order: **merge isolation** under parallel drafting (a monolith makes every batch a diff against one giant file); **git-native archaeology** (`git log` per requirement, free); the **identity scheme depends on it** (activation renames files; allocation reads the listing); **immutability is checkable per file**; **atomic review units** at Gate 1. Manifests are per-service (not per-fact) because a service's surface is reviewed and versioned as a unit and contention concentrates per service, not per key.

### 12.3 Read-path economics

Nothing hot reads many files: agents read packets; search reads the index; lints run incrementally; allocation reads the listing. Full scans (index regeneration, store-wide lints) are milliseconds over thousands of small YAMLs.

### 12.4 Forbidden middle grounds

- **One file per feature is FORBIDDEN** — the worst sharding key: parallel agents collide exactly where work concentrates.
- **A `NEXT_ID` counter file is FORBIDDEN** — races under branches; listing + serialized activation already solves it.
- Genuine limits far beyond ~10k RUs escalate to a database with files as source-of-truth export — never larger files.

---

## 13. Worked Examples

### 13.1 Example A — Order Lifecycle (statechart + manifest)

**The manifest fragment** — `spec/manifests/service-orders.manifest.yaml`:

```yaml
service: service-orders
version: "1.0"

problem_types:
  validation:   { uri: "urn:problem:validation",   status: 400, title: "Validation failed" }
  conflict:     { uri: "urn:problem:conflict",     status: 409, title: "Conflict" }
  unprocessable:{ uri: "urn:problem:unprocessable",status: 422, title: "Unprocessable" }

values:
  retention:
    decision_log_days: 90        # referenced by RU-0204 and RU-0301 (≥2 rule met)

audit_events:
  - { code: orders.cancelled,          fields: [order_id, actor, reason] }
  - { code: orders.screening.decided,  fields: [order_id, decision, reason_codes] }

endpoints:
  - { id: place_order,  method: POST,   path: /api/v1/orders,               access: protected, ru: FEAT-fraud-screening,    emits: [validation, unprocessable, orders.screening.decided] }
  - { id: cancel_order, method: DELETE, path: "/api/v1/orders/{id}",        access: protected, ru: FEAT-order-cancellation, emits: [conflict, orders.cancelled] }
```

**The model** — `MDL-order-lifecycle.statechart.json` (abbreviated) — dynamics only; every event resolves to manifest vocabulary (C8: `CANCEL` ↔ `{endpoint:cancel_order}`):

```json
{
  "id": "order-lifecycle",
  "initial": "pending",
  "states": {
    "pending":    { "on": { "CONFIRM": "processing", "CANCEL": "cancelled" } },
    "processing": { "on": { "CATALOG_UPDATED": "processing",
                            "CANCEL(order_id)": "cancelling",
                            "FULFILLED": "completed",
                            "PAYMENT_LOST": "failed" } },
    "cancelling": { "invariant": "no_new_shipments_dispatched",
                    "on": { "CANCEL_COMPLETE": "cancelled" } },
    "completed": { "type": "final" },
    "cancelled": { "type": "final" },
    "failed":    { "type": "final" }
  }
}
```

Conformance generation: one test per transition, one rejection test per undeclared (state, event) pair, one probe per invariant. Hand-editing generated tests FORBIDDEN — fix the model, regenerate. `CATALOG_UPDATED` as a self-transition encodes: catalog updates do not disturb in-flight orders (prices pinned at confirmation, same order_id).

**The RUs:**

```yaml
id: RU-0142
statement: >
  When a customer-support-agent calls {endpoint:cancel_order}, the system
  shall halt fulfilment activity for that order_id within 5 seconds.
syntax: ears
status: active
feature: FEAT-order-cancellation
source_ref: INT-0057#L34-41
rationale_ref: ADR-0031-cancellation-halt
verification:
  - type: model
    ref: MDL-order-lifecycle
    model_hash: "sha256:<computed>"
    conformance: generated
  - type: test
    ref: itest::orders::cancellation_latency_bound
scope:
  owns: [orders/fulfilment]
  must_not_touch: [payments/capture]
tags: [orders, cancellation]
```

Registration-rule note: the 5-second bound stays **literal** — it is used by exactly one RU, so §5.4 keeps it in the statement. The endpoint is referenced, never restated (interface surfaces always live in the manifest).

```yaml
id: RU-0143
statement: >
  While an order is cancelling, the system shall not dispatch any new
  shipments for that order.
syntax: ears
status: active
source_ref: INT-0057#L47-49
verification:
  - type: model
    ref: MDL-order-lifecycle
    model_hash: "sha256:<computed>"
    conformance: generated          # invariant probe from "no_new_shipments_dispatched"
scope:
  owns: [orders/fulfilment]
tags: [orders, cancellation, shipping]
```

```yaml
id: RU-0204
statement: >
  The system shall record every screening decision as {audit:orders.screening.decided}.
syntax: ears
status: active
feature: FEAT-fraud-screening
source_ref: INT-0102#L70-73
verification:
  - type: test
    ref: itest::screening::records_one_decision_entry
scope:
  owns: [orders/screening]
tags: [screening, audit]
```

What Example A demonstrates: timing lives in `test`, structure in `model`, facts in the manifest; the retention value is registered (≥2 RUs reference it) while the cancel bound stays literal; the audit event and endpoint are referenced by id; C8 binds the model's `CANCEL` to the manifest's surface; a later change of `decision_log_days` is a Gate-1 mutating edit whose impact report lists its dependents, and whose checks re-read the manifest rather than asserting a stale 90.

Note what RU-0204 does not say. Retention is declared on the audit event itself (§5.4) and one constitutional RU covers it for every record, so this statement asserts only the obligation that is its own: the record happens, exactly once. A fact declared in its proper home does not need restating once per event.

### 13.2 Example B — Story → RU compilation (where ACs went)

Traditional input (captured verbatim as `INT-0102`):

> *As an operations manager, I want to define fraud screening rules per sales channel so incoming orders are screened automatically without manual review.*
> AC1: manager can enable/disable screening per channel. AC2: on order placement with screening enabled, rules evaluate within 30 seconds. AC3: when an order is flagged, a customer-support-agent is notified with reason codes. AC4: every screening decision is logged with reason codes, retrievable for 90 days. AC5: if the screening engine is unavailable, the order is held pending-review and never auto-approved. AC6: where finding severity is critical, notification is also routed to the operations-manager channel.

Compiles to `FEAT-fraud-screening` plus six RUs — **one AC, one RU** — with the interface and value facts landing in the manifest:

| RU | Statement (abbreviated) | Verification |
|---|---|---|
| RU-0200 | Operations manager shall be able to enable/disable screening per channel | test |
| RU-0201 | When an order is placed via {endpoint:place_order} with screening enabled, rules shall evaluate within 30 seconds | test (latency) |
| RU-0202 | If the screening engine is unavailable at order placement, order shall be held pending-review and shall not be auto-approved | test + contract |
| RU-0203 | When an order is flagged, customer-support-agent shall be notified with the reason codes | test (delivery) + human (comprehensibility — Gate 2) |
| RU-0204 | System shall record every screening decision as {audit:orders.screening.decided}, retrievable for {value:retention.decision_log_days} days | contract + test |
| RU-0205 | Severity-based notification routing shall be resolved by MDL-severity-routing | model (decision table, diagram-as-source; severity vocabulary manifest-owned) |

What the compilation demonstrates: the narrative survives in INT and the FEAT goal; each statement carries more information than its source AC; mixed verification is normal (RU-0203's judgment is honestly `human`; RU-0205's matrix is a model consuming manifest vocabulary rather than six per-severity RUs); the 30-second bound stays literal (single RU), the 90-day retention is registered (shared); the human-readable story remains recoverable as a projection.

---

## 14. Scale Operations (hundreds of stories, ~1,500–2,000 RUs)

The mechanical layer does not strain at this scale (§12.3). Every genuine pressure point is human-attention-shaped:

| Pressure point | Failure mode | Countermeasure (normative) |
|---|---|---|
| Gate 1 throughput | Per-RU review ≈ 40h → rubber-stamping | Batch activation per feature (§8.2) |
| Context assembly on hot paths | One-hop overlap floods context | k=8 cap with feature/tag ranking (§9) |
| Conflict detection | Paraphrases evade parse-level C1 | Trigger normalization + analyst dedupe (§8.1) |
| Tag / actor entropy | Synonyms fragment ranking and conflict grouping | Controlled vocabularies (L10, L12) |
| Gap flood | Untriaged gaps ignored → silent guessing | `severity` field; only `blocking` holds activation |
| Human-verification debt | Human-only RUs accumulate quietly | Debt metric, monthly review (§6.4) |
| Untraced-check drift | Behaviour accrues that no RU governs | Orphan reports + L14 gate (§6.6) |
| Manifest churn | Frequent shared-fact edits ripple wide impact reports | Promotion-by-reuse rule (§5.5) keeps shared small; per-service manifests localize the rest |
| Over-registration | Statements degrade into symbol soup | ≥2 registration rule (§5.4), Gate 1 attention |
| Suspect-queue backlog | ADR/RU churn floods the queue; re-affirmations rubber-stamped | Suspect items batched into Gate 1 sittings; queue length is a tracked metric — sustained growth means rationale is churning faster than review capacity, a process finding in itself |

Standing rule: scaling fixes MUST target human throughput or context economy — never relaxation of verification. Weakening §5–§6 to go faster is the one adaptation this framework forbids.

---

## 15. Adoption Order

Adopt in this order. Each step makes the next one cheap, and every one of them
is useful on its own if you stop there.

1. **Scaffold.** `rqunit init` writes the store layout, the seed vocabularies, a
   coverage policy, and `rqunit.toml`. Declare your stack in the same sitting;
   an undeclared stack simply means the language-specific verbs observe nothing.
2. **Register the vocabularies you will actually use** — `tags.yaml` and
   `actors.yaml`. They start empty on purpose: a taxonomy chosen before there is
   content to classify is a taxonomy nobody obeys.
3. **Author one boundary.** A shared manifest, one service manifest, and a
   handful of RUs compiled from a real captured intent. Stop when
   `rqunit lint` and `rqunit check` are green and every reference resolves —
   that is the smallest thing that proves the model fits your domain.
4. **Wire the runtime hooks** so packet-scoped work is bounded (§10.3), and hold
   the first Gate 1 sitting: `rqunit activate batch`.
5. **Wire an adapter's extractor and scanner.** Conformance and traceability
   begin observing your code at this point; before it they have nothing to read.
   L14 blocks new untraced checks and existing ones burn down, so adoption never
   starts with a wall of red.
6. **Add models and generated conformance** once a lifecycle is worth pinning,
   and register the shim that makes the generated suite executable (§6.3).
7. **Set the coverage policy last** (§6.7), when there is enough RU volume to
   calibrate against. A policy written before content is a guess at profiles.

Three constitutional RUs are worth seeding early, because everything else is
measured against them: default-deny access, audit-on-mutation, and whatever
clean-room criterion your review process needs.
