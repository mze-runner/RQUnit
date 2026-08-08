---
name: ru-authoring
description: How to read, write, and MODIFY Requirement Units — EARS statement syntax, reference tokens, one-AC-one-RU compilation, GAP discipline, and the supersession rule (active RUs are frozen; L19 catches in-place edits). Load before authoring or changing ANYTHING under spec/ (RUs, FEATs, GAPs, manifests, models, ADRs, INT captures).
---

# Authoring Requirement Units

Normative sources (this skill summarizes, they win):
the framework specification and
the formats reference. Applies to every artifact under `spec/`.

## Reading an RU

One file = one RU under `spec/ru/`. The `statement` is the ONLY normative sentence; everything
else is machinery: `verification` (how it is proven — an RU without one is a preference),
`scope` (repo globs H1 enforces), `source_ref` (the INT line-anchor it was compiled from),
`gate1_stamp`/`link_fingerprints` (tool-written — NEVER hand-author). Search via
`spec/projections/ru-index.json`, not the directory.

## Writing statements — EARS (formats §3)

Exactly ONE normative clause per statement, terminated by a period. Five templates:

| Template | Shape |
|---|---|
| ubiquitous | `The system shall <response>.` |
| event | `When <trigger>, the system shall <response>.` |
| state | `While <state-condition>, the system shall <response>.` |
| unwanted | `If <condition>, then the system shall <response>.` |
| optional | `Where <feature-condition>, the system shall <response>.` |

Hard rules the linter enforces — write to them, don't fight them:
- The shall-clause subject is `the system` or a HYPHENATED service name (`service-orders shall …`).
  Actors NEVER take the shall ("Operations manager shall…" is an L1 error) — they live inside the
  trigger/condition (`When a user calls …`) and must be canonical ids from
  `spec/framework/actors.yaml` (L12; aliases rejected; register new actors FIRST).
- Bounds are a literal `number unit` ("within 5 seconds") or a `{value:…}` ref — never vague
  words (L2: no "quickly", "several", "reasonable"…). Single-use bounds stay literal; a value
  referenced by ≥2 RUs gets registered in the manifest (§5.4).
- Compound statements split (L3): "shall halt X and release Y" = two RUs; "shall log the actor
  and reason code" = one (compound object is fine).
- Never restate a fact the manifest owns (L17): no literal paths, subjects, wire types, or
  registered values in statements — reference them.

## Reference tokens (formats §2)

`{value:dotted.key}` `{endpoint:id}` `{problem:id}` `{audit:code}` `{message:id}`
`{channel:id}` `{frame:channel.frame}` `{vocab:name}` — resolved against the RU's scope service
manifest, then shared. Cross-service: `{endpoint:service-orders/cancel_order}` — qualified refs
resolve ONLY in the named manifest, are allowed for surfaces + problem/audit only, and NEVER for
values (a foreign scalar is the promotion-to-shared trigger). Literal braces escape as `{{ }}`.

**Endpoint shapes.** `{endpoint:id.outbound.field}` / `{endpoint:id.inbound.field}` addresses a
declared field of a surface; nesting rides in the field name
(`{endpoint:get_order.outbound.cancellation.at}`), and a bare `{endpoint:id.outbound}`
names the whole census. This is how a statement about a *shape* binds — an RU asserting a field
never leaves, or that a client may not set it, cites the field rather than describing it. The
direction set is closed: a misspelling is a malformed token, not an unresolved one. Summary only —
the linter is the law (spec §5.9, formats §13).

## Compiling requirements (the analyst's remit, spec §8.1)

- Input is an immutable INT capture under `spec/intent/` (verbatim human words — never authored
  prose). Every RU's `source_ref` anchors into it with real line numbers (L4 checks the range).
- **One acceptance criterion = one RU.** The story narrative → the FEAT `goal` (one sentence, no
  normative keywords — L11). Interface/value facts → the manifest, referenced by token.
- Ambiguity NEVER gets defaulted: unstated bounds, actors, triggers → a GAP artifact
  (`spec/gaps/GAP-<ULID>.yaml`, severity `blocking` holds activation; `clarify-later` doesn't).
  Zero gaps from substantial intent is itself a red flag. Inline `# CONFLICT:` comments are
  BANNED — a conflict is a blocking GAP.
- Never fabricate a `test`/`model` ref — use `TODO(<description>)` (the RU honestly
  computes *blocked*). Real test refs use `<cargo-package>::<file-stem>::<fn>`.
- Wire shapes are MANIFEST facts, not a separate artifact: a surface declares its census inline
  (`inbound`/`outbound`), and a structure hidden behind an encoding boundary — a JWT's claims
  inside `access_token: string` — is a shared `artifacts` entry the field names via `artifact:`.
  RUs never restate a census; they ADDRESS it with a token
  (`{endpoint:get_order.outbound.cost_basis}`, `{artifact:jwt-access-token.iss}`) and prove it
  with a test. Memberships = C5; census well-formedness = C11; editing a manifest flips
  dependents suspect (L20).
- Drafts are `spec/ru/RU-draft-<ULID>.yaml` (Crockford ULID, alphabet excludes I L O U);
  permanent ids arrive only at activation.
- If the store carries `spec/framework/segments.yaml`, a draft declares which domain it
  belongs to: `segment: ORD`, one of the names that file lists. The permanent id becomes
  `RU-ORD-01A2`, and NO segment means the requirement governs the whole store — which is
  the constitutional tier, the only one allowed to own nothing. Declare it, never derive
  it from `scope.owns`: a domain can span several services and one service can host
  several domains. L27 warns on a draft whose declaration contradicts its tier, in either
  direction. This is the last moment the choice is free — a permanent id can never acquire
  or shed a segment, because renaming ids is not a thing this framework does. A store with
  no segments file has no segments, and drafts omit the field entirely.
- Non-obvious decisions get an ADR: `spec/rationale/ADR-<slug>.md` (headings per formats §10:
  Context, Decision, Alternatives, Consequences) linked via `rationale_ref: ADR-<slug>` — a
  dangling ref is an L7 error. ADRs are editable prose; once a stamped RU fingerprints one,
  editing it flips that RU suspect (L20). Adding `rationale_ref` to an ACTIVE RU is a legal
  non-normative edit (outside the stamp hash) — `rqunit activate restamp` records the fingerprint.

## MODIFYING an RU — supersession, never editing

At activation, `statement`, `scope`, `verification`, and `tier` FREEZE — the gate stamp hashes
them, and L19 turns any in-place edit into a blocking error ("changed AFTER review"). The only
legal changes to an active RU are tags and typo-class fixes to non-normative prose. To change
meaning:

1. Write a NEW draft with the corrected statement and `supersedes: RU-XXXX`.
2. Anchor it to intent — the reason for the change is itself new intent (new INT capture).
3. Activate at a Gate 1 sitting: `rqunit activate batch … --reviewer <handle>` — the tool
   assigns the id, flips the target to `superseded`, stamps, and fingerprints atomically.

Manifest facts change differently: a mutating manifest edit passes Gate 1 WITH its impact report
(`rqunit impact`), and every frozen RU referencing the fact keeps meaning through the reference.

TODO refs resolve WITHOUT supersession: when the promised check exists, run
`rqunit activate resolve --reviewer <handle> RU-XXXX=<test id>` — the target must exist in
the trace scan, `--match <substring>` disambiguates multiple TODOs. Strictly strengthening;
weakening stays supersession-only. Never hand-edit the ref (L19).

Models change through re-affirmation: after editing a referenced statechart, run
`rqunit activate reaffirm --model MDL-<id> --reviewer <handle>` — it re-stamps every active
dependent whose meaning survives the change (supersede the ones whose meaning it alters).
Never hand-edit a `model_hash` (L19); superseded RUs keep historical hashes (L6 ignores them).
A model's generated suite drives a shim the APPLICATION provides. Until that shim is recorded in
`spec/framework/shims.yaml` (checked by C15), the suite is rendered unrunnable and its
verification counts as ZERO depth — so a `model` entry alone will not satisfy a mechanical
minimum, and a draft relying on one cannot activate until the shim lands. A suite that cannot
execute is not depth. The dialect itself is checked too (M1-M4/M6): `initial` must name a
declared state, transition targets must exist, final states carry no `on`, and invariant names
are unique — generation refuses a model whose violation would make the rendered suite wrong.

## Non-negotiables

- Reviewer/operator ids are stable handles (`<your-handle>`), NEVER emails — schema + CLI reject `@`.
- Tags must exist in `spec/framework/tags.yaml` first (L10); grow it in the same change.
- Coverage policy (`coverage.policy.yaml`, L21) is DATA, and the shipped default is a starting
  point the consumer tunes: constitutional RUs need ≥2 mechanical verifications; `security`-tagged
  need 2 mechanical, all of type `test`, and `binds_shape`; `audit`-tagged need `binds_shape`.
  `binds_shape` reads the STATEMENT — the RU must ADDRESS a declared shape by token
  (`{endpoint:…}`, `{audit:…}`, `{artifact:…}`), since depth without relevance proves nothing
  about the shape in question. Under-covered drafts cannot activate. A `model` entry whose shim
  is unregistered counts as no depth at all (see above).
- A `test` ref names a check that must EARN its green. A check written against an implementation
  it has already read can assert that implementation's shape and never fail — it reads as
  coverage and proves nothing. Author checks before the code where you can
  (`rqunit assemble build … --mode check-authoring`), run them expecting red, and record that run
  with `rqunit evidence record`. L26 reports, as a finding, any check observed green and never
  red.
- After ANY spec/ change run: `rqunit lint && rqunit check &&
  rqunit generate all` (projections are committed and currency-checked).
