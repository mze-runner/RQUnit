# Changelog

What changed in each revision of the specification, and what a consumer
must do about it. The [specification](docs/ru-framework-spec.md) and
[formats reference](docs/formats.md) describe the product as it is now;
this file is the only place that describes how it got here.

## v0.17.0

The credential a surface requires becomes a checkable relation, and several
things the tools claimed but did not do begin doing it. **C17** binds each access
tier to the credential that admits it: every tier a declared surface uses
resolves to exactly one `artifacts` entry carrying that `access_tier`, or is
listed in the new shared `credential_free_tiers`. C5 validated membership on both
sides and never related them, so a protected surface with nothing describing what
protects it, two credentials claiming one tier, and a tier in use that nothing
modelled all passed — a door with no stated lock read exactly like a door with
one. The binding is DERIVED through the tier string and there is no `artifact:`
key on an endpoint: a second path would make one fact expressible twice and let
`access: protected` sit beside a scoped credential. Exactly one artifact per tier,
because a tier admitting two shapes cannot tell a test what to send; if both are
genuinely accepted they are two tiers. `artifacts.<id>.fields` now references the
one census dialect the other three slots already used, so **`fields: none` is
legal** — the honest census for an opaque token, and what makes the binding total:
an artifact has two jobs, describing internals where they exist and naming the
credential in every case. **C11 extends over the artifact census**, previously the
only census in the manifest that was neither canonicalised nor checked, and the
slot holding the security-relevant shapes: a credential is minted rather than
accepted, so it takes the outbound presence vocabulary — `presence: optional` on a
claim asserted nothing and passed every gate — while `where` (claims vs header)
remains legal here and only here. **Artifacts are shared by construction:** the
schema now refuses an `artifacts` table on a service manifest, because C5 resolves
a field's `artifact:` reference against the shared table alone, so a service-local
one validated, sat in the manifest, and could never be pointed at. The
promotion-by-reuse sentence that suggested otherwise was already contradicted by
§5.5 and by formats §16's own title; §5.5 now names artifacts as its exception.

**L4 covers every artifact that declares a `source_ref`, not only RUs.** A FEAT
carries one under the identical grammar and nothing resolved it for eleven
revisions: the schema pattern enforced the anchor's SHAPE, so the link read as
covered while pointing at nothing. It is load-bearing rather than cosmetic,
because a manifest endpoint's required `ru` link admits `FEAT-<slug>` — the
incremental adoption path — so a surface's whole traceability chain could
terminate at a FEAT anchored into a file that no longer exists, and it bites
migration hardest, where captures are re-cut and line ranges move under anchors
nobody re-checks. **Reports name the version that produced them.** `tool_version`
was a hardcoded constant for fifteen minor releases, so every committed report
claimed `0.1.0` and no consumer holding one could tell what enforced it; it now
comes from the installed package, and `rqunit --version` answers both versions a
report carries, because answering one alone is the confusion `pack.yaml` exists to
explain. **A first-party adapter's manifest ships inside the tool.** `doctor`'s
only note on a fresh store instructed the reader to point `manifest = "…"` at a
file that existed only inside this repository, and the default it resolved
against — `<store>/adapters/<stack>/adapter.yaml` — asserted this repository's own
layout onto every consumer. The vocabulary a stack's passthrough keys are
validated against now ships in the pack, so a typo is named out of the box where
it previously read as configured; the `manifest` key remains, for an adapter this
build does not carry. Obtaining the adapter BINARIES is still your build's job.

**Intent admits the documentation a consumer already had.** §4 read as though only
transcripts and chat exports qualified, while the handbook and the shipped
`spec-store` skill documented capturing an existing corpus verbatim — three
statements, one of them wrong. Verbatim constrains FIDELITY, not genre: a capture
asserts that these are its source's words unedited, never that the source was
informal or spoken, and adopting over an existing corpus is the expected case
rather than an exception to argue for. No lint can check that words are unedited,
and §4 now says so. **`rqunit init` seeds `spec/framework/segments.yaml` empty**,
beside the tag and actor vocabularies its own loader always said it belonged with.
Declaring no segments stays a complete choice and an empty registry is
byte-identical in effect to an absent one — but the default was previously reached
by OMISSION, and an id's segment is the one decision in a store that cannot be
revisited, so the seed discloses that a choice exists while it is still free.
**CF8 stops misfiring on type-erased responses.** The Rust adapter reported
`Response` — what every axum handler returns after `.into_response()` — as though
it named a shape, so two endpoints serving entirely different bodies were reported
as contradicting each other, worsening with every endpoint declared. An adapter
now reports `type_name` only when the name identifies a shape; core already
skipped the comparison when none arrives, so there is no core change and no
contract change. The same walk also reported a handler's ERROR type as the shape
served when its success type was erased.

Reporting gets quieter about nothing and louder about what is true. **An empty
store says so** — `lint`, `check` and `doctor` on a store with no requirements
produced output indistinguishable from a mature healthy one, and "structurally
sound" was true and useless; it is a `finding`, so no exit code moves, and it is
keyed on having no RUs at all rather than on a count. **Output shape follows the
destination:** text at a terminal, JSON when piped, one rule across `lint`,
`check`, `conformance` and `doctor`, where previously `doctor` printed prose and
the others JSON — `--format` still overrides in both directions, and piping
`doctor` now yields JSON where it used to yield prose. **`lint` no longer crashes
on a read-only store:** it owns one projection and refreshed it outside the error
handling, so a read-only checkout or container mount ended the run with a
traceback instead of one of the three documented exits; the refresh is now
announced on stderr when it happens, and only when it happens. **Rule messages
state their invariant instead of citing `RU-0002`** — an id that exists in no
consumer store, since `init` seeds none, and the mirror image of the leakage rule
this product enforces on itself. **L24 asks instead of choosing** when several
registered values equal the same literal: it named both candidates and then
suggested the alphabetically first, which in a framework built for agent
participation is the half that gets applied. **Every schema refusal names its
key** rather than echoing the offending table back — `endpoints` on a shared
manifest was the worst case, being a plausible first mistake. **`init` names the
runtime files it wrote**, since `.claude/` is commonly gitignored and a count left
nothing to reconstruct from.

Documentation closes six questions a real onboarding run had to answer by reading
source: a surface may link a `FEAT-<slug>` and land before its requirement exists;
facts land with the first surface, and a fact with no surface belongs in `shared`;
one extracted surface per service, 1:1 with its manifest, because a stack table
binds an adapter rather than a service; "artifact" means both a store artifact and
a file a probe produced, now told apart in formats §1; `planned: true` versus a
GAP is decided by whether the facts are settled; and a manifest deliberately
carries no reference to prose.

**Consumers MUST act:** re-anchor every FEAT the upgraded `rqunit lint` reports —
the anchor was always broken and only now resolves; and for every access tier a
declared surface uses, either declare the credential under shared `artifacts` with
that `access_tier` (`fields: none` for an opaque token) or list the tier in
`credential_free_tiers`, which is a claim worth having on the record rather than a
waiver. Move any service-local `artifacts` table into the shared manifest — every
reference into it was already an error — and fix any artifact census using an
inbound presence value (`required | optional | forbidden`), which asserted nothing
about a structure nobody sends you. **Nothing else requires action, with one shape to check:** the version
reporting, the bundled adapter manifest, the seeded segment registry and the
CF8 fix are all strictly better answers to the same questions, no store turns red
for them, and an existing store's absent `segments.yaml` keeps meaning what it
meant. The one thing to look at is any script that PIPES `rqunit doctor` and
parses prose — it now receives JSON, and `--format text` restores the old shape.

## v0.16.0

Adapters become pluggable processes. Any
`[stacks.<name>]` table declares a stack — core carries no language list — and
core interprets a closed key set per stack (the `adapter` role declarations
and `literal_scan`); every other key is adapter-owned passthrough, validated
by the adapter manifest's `config_keys`, never by core. Each role runs out of
process behind a pinned schema, declared `cmd` (core execs the argv as an
opaque black box — never a language toolchain or build system) XOR `artifact`
(a file the stack's own pipeline produced). Three interface contracts join
`actual-surface` and `test-plan`: `scanned-checks` (scanner output),
`emit-request`/`emitted-files` (emitter stdin/stdout — files as data, core
writes every one, and check identity flows through the response's plan-check
mapping, never through parsing emitted source); the `adapter-manifest`
self-declaration carries roles, `config_keys`, and the compliance kit that
`rqunit adapter verify` runs. The statechart dialect's M1–M4/M6 move from
prose to enforcement as their own lint family, and generation refuses a
violating model with the same messages — a wrong model used to render a test
asserting a transition to nowhere. Shim registration becomes a recorded claim
(`spec/framework/shims.yaml`, checked by C15): an unregistered model's suite
is rendered unrunnable, contributes zero depth to the coverage policy, and is
reported apart from suites that execute — the last place
declared depth could exceed provable depth. Packets gain a `mode`: `check-authoring` assembles the same context plus the
instruction to write the checks before the implementation and record their
first red — discipline the framework states rather than polices, made
checkable by the ledger below. Adoption becomes reversible: a fifth role, `stripper`, and
`rqunit trace --strip` remove the trace annotations adoption asked a consumer
to write into their own tests — orphans by default, `--all` for off-boarding,
nothing written without `--apply`, and a stack declaring no stripper reported
as un-strippable rather than swept clean (§6.6). Core decides which tokens are
stale; the adapter rewrites its own sources. A fourth probe role, `evidence`, and an append-only ledger at
`spec/check-evidence/` record which checks have demonstrated they can fail; L26
reports the ones that never have (§6.8). L14 newness becomes base-vs-head set difference
over scanner observations, never diff-line inspection (§6.6 states the
widened-scan and rename consequences). Permanent ids gain a base-32 sequence and an optional
segment: `RU-ORD-01A2`, four Crockford characters per segment rather than four decimal digits store-wide, with the segments a store allocates into declared in `spec/framework/segments.yaml` and guarded by C16. Segments bound ALLOCATION and ownership, never verification — every rule stays store-wide, because a domain able to contradict another unnoticed is what a single shared store exists to prevent. A segment name is the one vocabulary here that is permanent: add and close, never rename or merge. Absence of a segment is a positive claim — this governs the store — which is the constitutional tier, and L27 reports a draft whose declaration contradicts its tier while the choice is still free (§7.1, formats §1). Gap-in-the-sequence detection retires with the decimal scheme, because under one base a gap between consecutive allocations is an artefact of the alphabet; `rqunit doctor` now compares what version control records as deleted against what the store still carries. Intents move to ULIDs for the reason drafts and GAPs already carry them — capture has no serialization point, so nothing can allocate an id, which is why nothing ever refused at the four-digit wall; the decimal form stays legal permanently and both coexist. The `source_ref` anchor TIGHTENS to lines only — `#S<slug>` is retired, having never been enforceable on a capture format without headings; **a store using one must convert it to the line range it meant**, which is what a reader had to work out anyway. **Consumers MUST act:** register a
shim in `spec/framework/shims.yaml` for every model whose suite really runs
(an unregistered one counts as no depth, so a draft relying on it can no longer
activate under a `min_mechanical` rule until the shim lands), declare
adapter roles in `[stacks.<name>.adapter]` — the extractor's write target
moves to `extractor = { artifact = "…" }` — delete `trace_diff`, and wire a
scanner role before using `rqunit trace --against`. Recording runs with
`rqunit evidence record` is optional: without it L26 simply has nothing to
report, which is the honest answer for a store that has observed nothing. **No id
migration is required and none is supported:** decimal ids are already valid base-32
ids whose reinterpretation preserves order, so every existing id keeps its spelling
and its place and the next allocation lands after all of them. Segments are opt-in —
a store that declares none carries none, and its drafts omit the field
## v0.14.0

One vocabulary — the manifest IS the
contract. `spec/contracts/` and the `contract` verification type retire; a shape
is a manifest fact and an RU binds to one by addressing it in the statement.
What the layer genuinely held — structure behind an ENCODING boundary, where a
census cannot reach — becomes `artifacts` in the shared manifest, referenced by
a field's `artifact:` and addressable as `{artifact:<id>[.<field>]}`; §6.1.
Audit becomes a full surface family: a census in the shared field grammar,
`retention` on the event, store-wide `audit_forbidden`, and `level` retired
because logging severity is the vocabulary of the thing audit is not; §5.10.
`emits` splits into `emits`/`audits`/`publishes` — three claims with three
audiences, where one list was ambiguous the day two registries shared a name —
and `publishes` closes an edge that never existed: an endpoint could not say
which message it published. Audit emission is reconciled at last (CF10/CF11);
C14 makes constitutional RU-0002 checkable as a finding; L25 checks the
statement subject, which the parser had only ever validated by shape; the
coverage policy gains `binds_shape`, which reads the STATEMENT so that
retiring `contract` strengthens rather than weakens what the policy can
require. **Consumers MUST act:** move every `CT-` file into shared `artifacts`,
convert `verification: contract` entries to a statement token plus a test, move
audit codes out of `emits` into `audits`, and drop `audit_events[].level`
## v0.13.0

The HTTP surface becomes bidirectional —
endpoints declare `inbound` and `outbound` field censuses inline, both
mandatory with `none` as an explicit declaration (C10); `success_status`
retires into `outbound.status`; presence is direction-keyed (`always|never`
outbound, `required|optional|forbidden` inbound) and joined by
`unknown_fields`, `nullable`, nesting via dotted field names, arrays, and a
closed bound-key set whose values reference `values`; wire naming is declared
once in the shared manifest under `conventions` and enforced by C13; the
reference-token grammar gains `{endpoint:<id>.<direction>[.<field>]}`; §5.9,
formats §2 and §13. **Consumers MUST act:** every endpoint declares both
directions, and any `success_status` key moves into `outbound.status`
## v0.12.0

The store carries a pack pin —
`spec/framework/pack.yaml` records the specification version a store was authored
against, and JSON Schemas move out of `spec/framework/` into the tool, so a
store is validated by the schemas of the version enforcing it; §12.1, formats
§8. Consumers scaffolded by an earlier version: nothing to do — an unpinned
store reports the enforcing version
## v0.11.1

TODO-resolution path — `resolve` converts TODO refs to real same-type refs at Gate 1 without supersession, §6.5
## v0.11.0

The contracts (CT) declaration layer — `spec/contracts/CT-<slug>.yaml`, kind `claim-set`, `access_tier` binding, endpoint `scope` field with `token_scopes` vocabulary, L5 resolution, C5 membership, packet rendering, manifest-like governance via content fingerprints
## v0.10.5

Model evolution gets its lawful path — `reaffirm` re-stamps active dependents of an edited model under the reviewer's id; L6 scopes to active/draft RUs, superseded hashes read as provenance
## v0.10.4

L2 scans authored prose only — reference-token spans are masked before vague-term scanning, closing the hyphenated-identifier false positive
## v0.10.3

ADRs live in-store at `spec/rationale/ADR-<slug>.md` — dangling `rationale_ref` is an L7 error, packets inline ADR content, format in formats §10
## v0.10.2

Token key grammar admits hyphens — schema/grammar consistency; v0.10: cross-service reference qualifier; `success_status` on endpoints; `planned` surfaces with asymmetric conformance + L22 backlink lint; `external` message producers; C9 message-topology check — dispositions of the six Phase-2 adoption GAPs