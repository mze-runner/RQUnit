# Changelog

What changed in each revision of the specification, and what a consumer
must do about it. The [specification](docs/ru-framework-spec.md) and
[formats reference](docs/formats.md) describe the product as it is now;
this file is the only place that describes how it got here.

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