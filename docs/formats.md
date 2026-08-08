# RU Framework — Formats & Conventions Reference

Companion to `ru-framework-spec.md` v0.10 and the adoption plan v1.0 (incl. tasks 052–055, C9/TASK-048). This
document pins every format the plan previously left implicit. It is normative
for tooling; changes are schema-revision events, not edits.

---

## 1. Identity & filename conventions

| Artifact | Filename | Id form |
|---|---|---|
| RU (draft) | `spec/ru/RU-draft-<ULID>.yaml` | `RU-draft-<ULID>` (Crockford base32, 26 chars) |
| RU (permanent) | `spec/ru/RU-<SEQ>.yaml` or `spec/ru/RU-<SEGMENT>-<SEQ>.yaml` | `RU-` + optional segment + 4-character base-32 sequence |
| FEAT | `spec/features/FEAT-<slug>.yaml` | `FEAT-<slug>` |
| GAP | `spec/gaps/GAP-<ULID>.yaml` | `GAP-<ULID>` |
| Manifest | `spec/manifests/<service>.manifest.yaml` | service slug; `shared` reserved |
| Model | `spec/models/MDL-<id>.statechart.json` | `MDL-<id>` |
| ADR | `spec/rationale/ADR-<slug>.md` | `ADR-<slug>` (pattern `ADR-[A-Za-z0-9-]+`) |
| Packet | `spec/packets/TASK-<id>.packet.md` (re-runs: `.v2`, `.v3` suffix before `.packet.md`) | task id from the operator's task system |

Filename ↔ `id` field mismatch is an L9 error.

**The sequence** is exactly four characters from the Crockford base-32 alphabet
`0123456789ABCDEFGHJKMNPQRSTVWXYZ`, zero-padded. I, L, O and U are excluded so
they cannot be read as 1 and 0; the alphabet ascends in ASCII order, so
lexicographic sort is allocation order. Case is never folded and the excluded
characters are never accepted: an id has exactly one legal spelling.

A store carries ONE base. Decimal-spelled ids remain legal and are read as
base-32 — `RU-0142` is 1346, not 142 — which is what lets a store that started
decimal continue in base-32 without rewriting a single id: the reinterpretation
preserves order, so every existing id keeps its spelling and its place, and the
next allocation lands after all of them. Reading one store in two bases is the
failure this rule exists to prevent.

**The segment** is optional: 2–8 characters, uppercase, beginning with a letter,
and never anything the sequence alphabet can spell — `CART` would make `RU-CART`
ambiguous, while `AUTH` and `ORDS` are fine because U and O are not in the
alphabet. Each segment is its own sequence, and the unsegmented space is a space
like any other. A draft names the space it will be allocated into with a
`segment` field; the field is consumed at Gate 1, because from then on the id
carries the fact and a second copy could disagree with it. Segments are declared
in `segments.yaml` (§14c) and must be declared before their first id is minted.

The four-character width is a CEILING, not a default: it is compiled into every
schema pattern, filename and cross-reference, so widening it is a store-wide
migration in one commit — every id renamed, every reference rewritten, never
mixed widths and never mixed bases. The ceiling is per segment, so allocating
into another segment is usually the nearer answer. Activation refuses rather
than crossing it, and `rqunit doctor` warns per space while there is runway.

## 2. Reference token grammar (EBNF)

```
token      = "{" kind ":" [ qualifier "/" ] key "}" ;
kind       = "value" | "endpoint" | "problem" | "audit"
           | "message" | "channel" | "frame" | "vocab" ;
qualifier  = ident ;                       (* owning service slug (v0.10);
                                                   FORBIDDEN for kind "value" —
                                                   foreign scalars promote to shared *)
key        = dotted | frameref | surfaceref ;
dotted     = ident { "." ident } ;              (* value: dotted; others: single ident,
                                                   audit: dotted event code *)
frameref   = ident "." ident ;                  (* frame only: channel.frame *)
surfaceref = ident [ "." direction [ { "." fieldname } ] ] ;
                                                (* endpoint only *)
direction  = "inbound" | "outbound" ;
ident      = lowletter { lowletter | digit | "_" | "-" } ;
                                                (* v0.10.2: "-" admitted so RFC 7807-style
                                                   hyphenated keys (problem types, service
                                                   slugs) are referenceable; the qualifier/key
                                                   split stays unambiguous — "/" delimits *)
fieldname  = letter { letter | digit | "_" | "-" } ;
                                                (* mixed case admitted: `conventions.field_names`
                                                   decides which convention is legal in a store
                                                   (C13), and the grammar must not pre-empt that.
                                                   Identical to manifest `$defs/field_name`'s
                                                   segment — widening either alone is a red build *)
```

An `endpoint` key addresses a surface, optionally one of its two directions,
optionally a path into that direction's declared census — nesting is expressed
by the field name itself (`cancellation.at`), matching the manifest.
`direction` is closed by the grammar, so a misspelling is **malformed**, not
merely unresolved: the mistake is in the reference, not in the manifest. A
direction declared `none` resolves — "this surface carries nothing" is a
positive claim — while an absent direction does not, which is what lets C10
tell a deliberate empty from an unfinished declaration.

Resolution: a qualified ref resolves against the named manifest ONLY (a miss
is unresolved, L15 — never a fallback to own-scope or shared); an unqualified
ref resolves own-scope service manifest → `shared.manifest.yaml`.
Literal braces in statements are escaped `{{` `}}`.
Unknown kind, empty key, nesting, or a qualified `value` ref → tokenizer error
(feeds L15's "malformed" class, distinct from "unresolved").

## 3. EARS grammar (normative for TASK-011)

Statement = one template instance, terminated by a period. `<system>` is the
literal phrase "the system" or a manifest service name. `<actor>` must resolve
to `actors.yaml` (L12). `<bound>` = number+unit or `{value:…}` token. Case
of leading keyword: capitalized as shown.

```
ubiquitous = <system> " shall " <response> "."
event      = "When " <trigger> ", " <system> " shall " <response> "."
state      = "While " <state-cond> ", " <system> " shall " <response> "."
unwanted   = "If " <condition> ", then " <system> " shall " <response> "."
optional   = "Where " <feature-cond> ", " <system> " shall " <response> "."

trigger    = <actor-phrase> | <event-phrase>          (* actor extracted when present *)
response   = verb-phrase [ " within " <bound> ] [ qualifiers ]
```

Negative responses ("shall not …") are valid responses. A statement matching
no template, or matching one with an unfillable slot, is an L1 error carrying
the nearest-template diagnosis. Compound detection (L3) operates on the parsed
`response`: two coordinated shall-clauses = compound; one shall-clause with a
coordinated object = single. The TASK-011 golden suite is the executable
definition of edge cases — extend the suite before extending the grammar.

## 4. Violation report format (all CLIs)

stdout, JSON, one document per run:

```json
{
  "tool": "spec-lint",
  "tool_version": "0.1.0",
  "store_commit": "<git sha or WORKTREE>",
  "generated_at": "<iso8601>",
  "summary": { "errors": 2, "warnings": 1, "checked_files": 41 },
  "violations": [
    {
      "rule": "L2",
      "severity": "error",              // error | warning | finding
      "artifact": "RU-0142",
      "path": "spec/ru/RU-0142.yaml",
      "line": 3,
      "message": "Unbounded quantifier 'quickly' in statement bound position.",
      "suggestion": "State a literal bound or reference a manifest value: {value:...}."
    }
  ]
}
```

`finding` severity = report-only rules (C7, orphan reports): never affects
exit code. Exit codes: 0 no errors (warnings allowed unless `--strict`),
1 errors present, 2 tool failure. Human-readable rendering is `--format text`,
derived from the JSON, never a separate code path.

## 5. Trace annotation conventions (`verifies`)

| Where | Form |
|---|---|
| Python tests | `@pytest.mark.verifies("RU-0142")` (repeatable) |
| Rust tests | doc-comment line `/// verifies: RU-0142[, RU-0143]` directly above `#[test]`/`#[tokio::test]` |
| Generated conformance suites | no per-test annotations — a sidecar `spec/projections/trace-map.json` `{ "check_id": ["RU-…"] }` emitted by the generator from the model's RU links |
| Infrastructure tests | `verifies: infrastructure` (audited bucket, §6.6) |

`spec-trace` resolves all four sources; an id failing the permanent-id pattern (§1) or
resolving to no active RU is an L14 error.

## 6. Task packet layout

`TASK-<id>.packet.md`, sections in this exact order (golden-packet tests
depend on it):

```
---                                  # YAML front matter
task: TASK-0007
mode: implementation                 # implementation | check-authoring
generated_at: <iso8601>              # the only nondeterministic field
store_commit: <sha>
hashes:
  manifests: { service-orders: "sha256:…", shared: "sha256:…" }
  models:    { MDL-order-lifecycle: "sha256:…" }
---
# 0. Constitutional requirements        (full RU renders)
# 1. Task requirements                  (full RU renders, refs RESOLVED inline:
#                                        "within 90 days ⟨{value:retention.decision_log_days} = 90⟩")
# 2. Interface star map                 (per touched service: endpoint table,
#                                        messages, channels+frames, referenced
#                                        problem/audit entries, relevant values)
# 3. Rationale                          (linked ADR contents)
# 4. Background (read-only)             (k≤8 one-hop RUs, statement-only,
#                                        then "Further: RU-…, RU-…" id list)
# 5. Boundaries                         (owns / must_not_touch union, verbatim
#                                        globs H1 will enforce)
# 6. Authoring discipline               (check-authoring packets ONLY: write the
#                                        checks before the implementation, do not
#                                        read the owned files, record the first red)
```

`mode` records which discipline produced the packet. `check-authoring` appends
section 6 and nothing else: no hook gates reads, and the packet says so. What
makes the discipline checkable afterwards is the evidence ledger (spec §6.8) —
a check authored before its implementation is observed red first, and one that
was only ever green is reported by L26 whatever the packet instructed.

An RU render = id, statement (resolved), verification list with current
computed status, tags. Resolution provenance format is fixed: `⟨{ref} = value⟩`.

## 7. Index format

`spec/projections/ru-index.json`:

```json
{ "generated_at": "…", "store_commit": "…",
  "rus": [ { "id": "RU-0142", "status": "active", "tier": "standard",
             "computed": "done", "tags": ["orders","cancellation"],
             "feature": "FEAT-order-cancellation",
             "owns": ["orders/fulfilment"], "must_not_touch": ["payments/capture"],
             "verification_types": ["model","test"],
             "manifest_refs": ["endpoint:cancel_order"] } ] }
```

## 8. Seed data

`lints/vague_terms.yaml` (L2 wordlist, data not code — extend by PR):

```yaml
bound_position:   [quickly, soon, promptly, immediately, "in a timely manner", eventually, "as soon as possible", asap]
quantity_position: [many, few, several, some, large, small, numerous, various, appropriate, sufficient, reasonable, adequate, minimal]
```

("immediately" is vague — an agent cannot test it; the fix is a literal bound.)

`shared.manifest.yaml` seed (required before any endpoint validates, because
`access` tiers are a vocabulary, not a schema enum):

```yaml
service: shared
version: "1.0"
vocabularies:
  access_tiers: [public, internal, partner, protected]   # operator-tunable
```

**Pack pin** — `spec/framework/pack.yaml`, written when the store is
scaffolded and thereafter edited only by a deliberate upgrade:

```yaml
pack: "0.14.0"
```

It records the **specification** version — the vocabulary the store's manifests
and RUs are written in — not the tool version. The two move independently on
purpose: a tool fix (a crash, a message) changes no vocabulary, and forcing a
spec revision for one would make every consumer re-read a document that did not
change. `rqunit` reports both, as `framework_version` (this pin) and
`tool_version` (the package doing the enforcing), and they are expected to
differ.

It records the pack version the store was **authored against**, which is not
necessarily the version enforcing it today; the pin is reported, never
reconciled. A store without the pin is unpinned, not invalid — reporting
falls back to the enforcing version.

## 9. Gate stamps & fingerprints (v0.9)

**Canonical hash** (gate stamps, RU-target fingerprints): JSON serialization of
the object `{statement, scope, verification, tier}` with keys sorted
recursively, UTF-8, no insignificant whitespace, `tier` defaulted to
`"standard"` when absent; hash = `sha256:` + hex digest. ADR-target
fingerprints: sha256 of the raw file bytes. One canonicalizer implementation,
exported by the store loader — L19, L20, and `spec-activate` MUST share it
(three implementations of "canonical" is how canonical dies).

**Gate 2 record** — `spec/reviews/<RU id>/<iso8601-basic>-<slug>.yaml`,
append-only (CI rejects modification/deletion of existing records):

```yaml
ru: RU-0203
criterion: "Is the rejection message comprehensible to a non-technical customer?"
verdict: pass            # pass | fail
note: "Clear at 8th-grade reading level; tone acceptable."
reviewer: "<operator id>"
at: "2026-07-21T10:02:00Z"
packet: TASK-0007        # the packet whose output was judged
```

`ru.reviewed` computation compares record `at` against `gate1_stamp.at`;
records predating the stamp never count.

## 10. ADR format

One decision per file at `spec/rationale/ADR-<slug>.md`; the id is the
filename stem. Section convention (recommended, not machine-parsed — the
store tracks ADR identity and bytes, never structure):

```markdown
# ADR-<slug> — <title>

## Context
## Decision
## Alternatives
## Consequences
```

Rules that ARE enforced:

- A `rationale_ref` that does not resolve to a store file is an **L7 error**.
- ADRs carry **no lifecycle states** — they remain editable prose. Governance
  is the byte fingerprint (§9) recorded on dependent RUs at activation: an
  edit flips every dependent suspect (L20), resolved at the next Gate 1
  sitting by re-affirm or supersede.
- `rationale_ref` sits outside the gate-stamp hash, so linking an ADR to an
  already-active RU is a legal non-normative edit (no supersession needed);
  `spec-activate restamp` records the missing fingerprint.
- Task packets inline the full ADR content in section 3 (§6).

**Operator identity (v0.10.1):** every reviewer/operator id in the store
(`gate1_stamp.by`, Gate 2 `reviewer`, fingerprint re-affirmations) is a stable
HANDLE (e.g. a VCS username), never contact information — the store is
published with the repository. Emails are schema-rejected (`by` pattern) and
CLI-rejected (`--reviewer`); the handle→person mapping lives outside the repo.

## 11. (retired — the contract layer)

`spec/contracts/CT-<slug>.yaml` and the `contract` verification type were
retired in v0.14. A shape is a manifest fact: a surface declares its census
inline (§13), and structure behind an encoding boundary is a shared `artifacts`
entry (§16). The section number stays spent — references in the wild point
here rather than at something else.

## 12. Open decisions ratified by this document (flag to operator, defaults active)

1. GAP ids are ULIDs (parallel creation, no ceremony) — resolution MUST anchor to INT.
2. Statechart dialect v1 is flat: no hierarchical/parallel states. Revisit only with a concrete need.
3. `undeclared_event_policy` is per-model, mandatory, `ignore|error` — no implicit behaviour.
4. Access tiers moved from schema enum to shared vocabulary (C5-checked) — projects tune the set without schema forks.
5. Packet re-runs are versioned files, not overwrites (immutability, §9.1).
6. Model `vocabulary` tokens are unqualified — own-scope binding only. A model
   binds to its service's own manifest entries; cross-service traffic reaches a
   model as the service's own inbound `message` entry. Deliberate; revisit only
   with a concrete cross-service-model need.

## 13. Surface shape format (v0.13)

An endpoint declares both directions; spec §5.9 is normative for what they mean.
Sections are numbered by arrival, so this one follows §12 rather than sitting
beside the other format sections — renumbering would break every reference.

```yaml
- id: list_order_items
  method: GET
  path: "/api/v1/orders/{order_id}/items"      # placeholders uniquely named (C12)
  access: protected
  ru: FEAT-order-read
  emits: [not-found]                            # problem responses live here, not in outbound
  inbound:
    unknown_fields: reject                      # overrides service `defaults`
    fields:
      - { name: order_id, in: path,  presence: required, type: string }
      - { name: limit,    in: query, presence: optional, type: integer,
          min: 1, max: "{value:paging.max_limit}" }
  outbound:
    status: 200
    fields:
      - { name: items,            presence: always, type: array, items: object }
      - { name: items.id,         presence: always, type: string }
      - { name: items.cost_basis, presence: never, note: internal pricing never leaves }
      - { name: next_cursor,      presence: always, type: string, nullable: true }
```

`inbound: none` and `fields: none` declare that the direction carries nothing.
An omitted direction declares nothing and is a C10 error.

Field keys: `name` (dotted for nesting), `presence`, `in` (inbound only,
default `body`), `type`, `items` (mandatory when `type: array`), `nullable`,
`vocab`, `note`, and the bound keys `max_chars`, `min_chars`, `min`, `max`,
`min_items`, `max_items`. A bound is a literal or a `{value:…}` reference; the
reference form is preferred and a literal duplicating a registered value is an
L24 finding. A field typed `object` declares at least one dotted child —
otherwise it is an unbounded blob wearing a type, which reads as specified
without being so.

The schema admits the union of both presence vocabularies and every bound key
on every type: applicability is C11's judgment, not the schema's, so a mistake
arrives as a message that teaches rather than as a parse failure. The same
split governs naming — the grammar admits mixed case and `conventions`
(§8, shared manifest only) decides which convention is legal, enforced by C13.
An absent `conventions` table means unenforced.

## 14. Ratified conformance divergences

`spec/framework/conformance-exceptions.yaml` — seeded empty by `rqunit init`,
edited at Gate 1 like any other reviewed decision. An absent file means none.

```yaml
exceptions:
  - rule: CF4                       # the divergence class this excuses
    service: service-orders
    target: "GET /api/v1/healthz"   # '<METHOD> <path>' for endpoints, the subject for messages
    justification: >
      `internal` is a network-policy tier enforced at the ingress rather than by
      route middleware, so the route is structurally public by design.
```

A matching divergence is downgraded from `error` to `finding` and reported with
its justification. It is never suppressed: an exception that outlives its reason
becomes camouflage, and the report is what surfaces it at the next sitting.

`justification` has a minimum length, checked on load. The rule that matters is
not structural — a one-word waiver satisfies any shape check and defends
nothing.

Adapters may not author these. An artifact carrying an `exceptions` key is
rejected as a configuration error naming this file, because an extractor
observes and does not get to excuse what it observed (spec §5.6).

## 14a. Shim registrations

`spec/framework/shims.yaml` — seeded empty by `rqunit init`. Records which
models have an application-provided subject shim, so their generated suites
can execute. An absent file means none registered.

```yaml
shims:
  - model: MDL-order-lifecycle      # with or without the MDL- prefix
    registered_by: jane             # stable handle, never an email
    at: "2026-01-15T09:30:00Z"      # when the shim landed
    note: subject("order-lifecycle") wired to the domain aggregate   # optional
```

A registration is a **depth claim**, checked by C15: one per model, naming a
model the store carries, each entry a table. Until a model is registered its
suite is rendered unrunnable, contributes zero depth to the coverage policy
(L21) — including its `types_all`/`types_any` clauses — and is reported
separately from suites that execute. Registering a shim that does not exist
is the one way to make the framework overstate what it can prove, which is
why the claim is a reviewed edit rather than an observation.

## 14b. The check-evidence ledger

`spec/check-evidence/check-evidence.jsonl` — append-only, written only by
`rqunit evidence record`. One JSON object per line, one line per check per
first:

```json
{"at": "2026-01-15T09:30:00+00:00", "check_id": "svc::orders::rejects_cancel_after_ship", "observation": "first_red", "source": "spec-conformance-tests/check-evidence.json"}
```

`observation` is `first_red` or `first_green`. Only firsts are recorded: a
second red proves nothing a first red did not. `check_id` shares the scanner's
identity space (`scanned-checks.schema.json`), which is what lets evidence
attach to a check an RU verifies against. A check carrying `first_green` and no
`first_red` is what L26 reports (spec §6.8) — the framework's evidence about
its own checks, never the consumer's audit record (§5.10).

## 14c. The segment registry

`spec/framework/segments.yaml` — the domains this store allocates ids into.
Consumer-owned and Gate-1-governed like the tag and actor vocabularies, but
unlike them it is NOT scaffolded: `rqunit init` writes no segments file, because
a taxonomy chosen at the moment a store knows least is the fastest way to a
taxonomy nobody obeys. The file is created when a store adopts its first
segment. An absent file means the store has none and its ids carry none, which
is a complete state rather than an unfinished one.

```yaml
segments:
  - name: ORD                       # the name its ids carry (§1)
    domain: order management — placement, amendment, cancellation
  - name: BILL
    domain: invoicing and settlement
    closed: true                    # allocates nothing further; its ids keep working
    note: folded into order management            # optional
```

Checked by C16: each entry a table, each `name` legal under §1 and declared
once, each with a stated `domain`, and every segment an id uses declared here.

**Two edits are supported: add a segment, and close one.** Activation refuses to
allocate into a segment this file does not declare, and refuses a closed one —
so closure is a working retirement path rather than a note. A segment name is
the only vocabulary in this store that cannot be corrected. It appears in
filenames, in gate stamps, in Gate 2 review directory names, in committed
packets, and in `verifies:` annotations inside the consumer's own source — and
ids are never rewritten — so renaming or merging a segment is a mass
supersession, not an edit. Removing an entry whose ids exist leaves them naming
a domain the store no longer declares; `closed: true` is the retirement path
that does not.

Segments bound **allocation and ownership, never verification.** C1 compares
RUs against each other, C9 spans services, and L13 caps constitutional RUs
store-wide — a limit that is only meaningful because it is global. No rule
partitions by segment, and none may.

## 15. Stack declarations (`rqunit.toml`)

Any `[stacks.<name>]` table declares a stack (`name` matches
`[a-z][a-z0-9_-]*`); core carries no list of supported languages. A missing
file means no stacks: store-only operations need zero configuration, and
stack participation is always an explicit declaration.

Per stack, core interprets a CLOSED key set; every other key is the adapter's
own configuration, passed through opaquely and never read by core.

**Core-interpreted keys:**

| Key | Meaning |
|---|---|
| `adapter.extractor` / `adapter.scanner` / `adapter.emitter` | role declarations — each `{ cmd = ["..."] }` XOR `{ artifact = "path" }` |
| `adapter.manifest` | path to the adapter's manifest |
| `literal_scan` | globs naming the FILES the hardcoded-bound advisory sweeps (`**/tests/*.rs`, `**/__tests__/*.js`) — the glob carries the language-specific fact, so core stays a word-boundary numeric match |

A role declares `cmd` (argv core execs, no shell) or `artifact` (a file an
earlier pipeline step produced) — exactly one. An undeclared role means that
capability is unavailable for the stack: reported as such, never silently
skipped.

```toml
[stacks.rust]
literal_scan = ["**/tests/*.rs"]

# ---- adapter-owned: core passes these through untouched --------------------
service = "service-orders"          # manifest slug the artifact is keyed by; never guessed
trace_scan = ["**/Cargo.toml"]

[[stacks.rust.routers]]             # one table per mounted router
file = "http/src/routes/orders/mod.rs"
function = "router"
prefix = "/api/v1/orders"
access = "protected"

[stacks.rust.messages]
subject_sources = ["wire/src"]              # where subject constants are declared
publisher_sources = ["adapters/nats/src"]   # code that references them

[stacks.rust.adapter]
extractor = { artifact = "conformance/actual-surface.json" }
```

Malformed shapes among the core-interpreted keys are errors: a typo silently
ignored would read as configured. Passthrough keys are validated by the
adapter — the framework judging what `routers` means would be language
knowledge — with key-name typo detection provided by the adapter manifest's
`config_keys`. Composition facts like `routers` stay configuration because
they are properties of one repository, not of a language: an extractor that
guessed a composition would report a surface nobody declared, and the
reconciler would believe it.

**Scanned checks** (contract: `interfaces/scanned-checks.schema.json`) — the
scanner role's output: the tests a tree carries and what each one's trace
annotation claims (`verifies`: RU ids, `["infrastructure"]`, or `[]` for
untraced). Check ids are stack-qualified so the union across stacks never
collides. `rqunit trace` owns every judgment over these observations,
including L14's set-difference definition of "new" (spec §6.6).

**Emit request / emitted files** (contracts:
`interfaces/emit-request.schema.json`, `interfaces/emitted-files.schema.json`)
— the emitter role's stdin and stdout. The request carries the test plan
(verbatim `test-plan.json` payload), each value-holding manifest's leaves and
hash, and the stack's passthrough options as data — an emitter is a pure
function of the request and never reads the store. The response returns files
as data plus the plan-check → stack-qualified-check-id mapping; core validates
that mapping against the plan's census (nothing dropped, invented, or
double-mapped), rejects any path escaping the consumer root, and writes every
file itself. An artifact-mode emitter owes a currency test in its own suite —
regenerate the response from the current request and compare — exactly as an
artifact-mode extractor does: the census catches a dropped or added check,
but a semantic change that keeps every check id (a flipped
`undeclared_event_policy`) only the currency test catches.

**Check evidence** (contract: `interfaces/check-evidence.schema.json`) — the
evidence probe's output: one entry per check the run executed, `passed` or
`failed`. It carries no timestamp, because a probe's bytes must be a
deterministic function of its input; core stamps the recording time.

**Adapter manifest** (`adapter.yaml`, contract:
`interfaces/adapter-manifest.schema.json`) — the adapter package's
self-declaration, read by core and never by the adapter. Located at the
declared `adapter.manifest` path, or `adapters/<name>/adapter.yaml` by
convention; a stack may run without one, forfeiting passthrough typo
detection.

```yaml
contract_version: 1
stack: rust                      # must match the [stacks.<name>] wired to it
roles: [extractor]               # a declared role the manifest lacks is surfaced before the exec fails
config_keys: [service, routers]  # the passthrough keys this adapter reads
kit:                             # what `rqunit adapter verify` runs (dev-time)
  path: kit                      # <kit>/<role>/tree/ input, <kit>/<role>/expected.json expectation
  commands:                      # argv relative to this manifest's directory
    extractor: [target/debug/extract-surface]
```

The kit is the executable definition of a correct adapter: every declared
role's fixed input must produce byte-deterministic, schema-valid output
matching the committed expectation, under the stdio exit contract. The
emitter's kit input ships with the tool (every emitter renders the same
generic request); probe inputs are the adapter's own trees.

## 16. Shared artifacts

`artifacts` in `spec/manifests/shared.manifest.yaml` — structures minted
somewhere, carried as a VALUE inside payloads, and validated elsewhere.
Credentials are the population; the test is whether a field census can reach
the structure, and for anything base64'd or signed it cannot.

```yaml
artifacts:
  jwt-access-token:
    access_tier: protected            # the tier whose surfaces consume it (C5)
    fields:
      - { name: sub, where: claims, presence: always, type: string }
      - { name: kid, where: header, presence: always }
      - { name: iss, presence: never }
```

Fields use the same grammar as every surface census (§13), plus `where`
(`claims | header`) — JWS vocabulary, and correct for the population it
describes. C11 rejects `where` on a surface census, where the position IS the
field name.

A field declares that its value is one of these with `artifact:`:

```yaml
- { name: access_token, presence: always, type: string, artifact: jwt-access-token }
```

That key sits beside `vocab:` and makes the same class of claim — one says which
values are legal, the other what structure the value has. A dangling reference
is a C5 error.

Promotion by demonstrated reuse applies (spec §5.5): an artifact used by one
service stays in that service's manifest, and only reaches `shared` when a
second needs it.

## 17. Audit records

```yaml
audit_common: [event, timestamp, actor, ip_address]   # every record carries these

audit_events:
  - code: orders.cancelled
    ru: FEAT-order-cancellation
    retention: "{value:retention.audit_days}"
    fields:
      - { name: order_id, presence: always, type: string }
      - { name: reason,   presence: always, type: string, vocab: cancellation_reasons }
```

Presence is the OUTBOUND vocabulary (`always | never`) — a record is minted,
never accepted. `retention` is a literal or a `{value:…}` reference.

Fields no record may EVER carry are declared once, store-wide:

```yaml
# shared.manifest.yaml
audit_forbidden: [password, raw_token, card_pan]
```

A census declaring one of those as `always` is a C6 error. There is no `level`:
trace/debug/info/warn/error is logging severity, and an audit record either
happened and must be kept or it did not.

Surfaces declare what they record with `audits:` — endpoints, and inbound
messages (an outbound entry produces a message rather than handling one).
