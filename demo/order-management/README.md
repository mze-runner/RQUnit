# Demo store — order cancellation

A complete, gated spec store. The fixture stores under `fixtures/` are
deliberately minimal and rule-scoped — `fixtures/checks/C11/fail` is not
something you would show anyone. This is the only place the whole vocabulary
is exercised together, and CI runs the gate over it, so it cannot quietly go
stale the way a prose example would.

## Run it

```bash
uv run rqunit lint        --store demo/order-management --format text
uv run rqunit check       --store demo/order-management --format text
uv run rqunit conformance --store demo/order-management --format text
uv run rqunit report      --store demo/order-management --out -
```

`lint` and `check` exit 0. `check` still prints findings — see below.

## Read it in this order

1. **`spec/intent/INT-0001.md`** — the raw human words, verbatim and
   immutable. Everything else is compiled from it, and every RU's
   `source_ref` anchors into real line numbers here.
2. **`spec/manifests/service-orders.manifest.yaml`** — the boundary. One
   entry per surface, both directions declared, nothing about behaviour.
3. **`spec/ru/`** — the behaviour. Notice what the statements never say: no
   field lists, no paths, no status codes, no retention window. Those are
   manifest facts, referenced by token.
4. **`spec/manifests/shared.manifest.yaml`** — cross-service facts, and the
   `artifacts` table.

## What to look at, and why

**`cancel_order` declares three different side effects.** `emits` is what a
caller can be told, `audits` is evidence nobody outside sees, `publishes` is
what subscribers receive. They were one list until v0.14, which was ambiguous
the day two registries shared a name.

**`refund_cents` is `forbidden` on the request.** The intent capture says a
client once sent the refund amount and the service used it. That single word
is the mass-assignment boundary, RU-0004 says what happens when a client sends
it anyway, and `ADR-refund-amount-is-server-derived` records why.

**`access_token` carries an artifact.** The census stops at the string; the
claims live inside it. `artifact: access-token` names what is in there, and
RU-0005 addresses one of those claims directly —
`{artifact:access-token.iss}` — which no payload census could reach.

**`refund_settled` is an inbound message that records audit.** Billing is
outside this store (`external: true`), and handling its event writes evidence.
Until v0.14 an async consumer had nowhere to say that.

**Retention lives on the audit event, not in the RUs.** Compare RU-0003 with
the pre-v0.14 idiom: every audit RU used to carry its own "retrievable for N
days" clause. The fact moved to its proper home and the clause disappeared.

## The findings are deliberate

`check` reports C7 orphans and one C14. They are `finding` severity — never
affecting exit code — and they are here because a store with nothing to report
teaches nothing about what the tool is for.

- **C7 orphans**: `get_order` and `issue_session` are declared surfaces no
  active RU governs yet. Real stores look like this mid-migration; the tool
  says so rather than staying quiet.
- **C14**: `cancel_order` is state-changing, and constitutional RU-0002
  requires an audit event for every state-changing action. It declares one —
  so the finding you see is on a *different* surface, which is the point:
  the rule is a heuristic on HTTP method and reports rather than blocks.

## Conformance

`actual-surface.json` is what a probe would emit, hand-written because the
artifact is a committed file by design — so the demo can show CF1–CF11 without
dragging a Rust toolchain into it. It deliberately spells paths as `:order_id`
where the manifest writes `{order_id}`: normalization means one route, not two
divergences.

The boundary line at the end of `conformance` output is the honest part —
some fields are extractor-confirmed, some are not reached by extraction at
all. A manifest is allowed to exceed what a probe can see; what it may not do
is let that difference go uncounted.
