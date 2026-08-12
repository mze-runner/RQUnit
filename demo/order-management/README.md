# Demo store — an order, end to end

A complete, gated spec store covering one order's whole life: a customer finds a
product, places an order, and the order is either cancelled or delivered. Two
services, eighteen requirements, one statechart, and every gate green.

The fixture stores under `fixtures/` are rule-scoped and deliberately minimal —
`fixtures/checks/C11/fail` is not something you would show anyone. This is the
only place the whole vocabulary runs together, and CI runs the gate over it, so
it cannot quietly go stale the way a prose example would.

## Run it

```bash
uv run rqunit lint        --store demo/order-management --format text
uv run rqunit check       --store demo/order-management --format text
uv run rqunit conformance --store demo/order-management --format text
uv run rqunit doctor      --store demo/order-management --format text
uv run rqunit report      --store demo/order-management --out -
```

`lint`, `check` and `conformance` exit 0. `lint` reports one warning and `check`
reports findings; both are explained below.

## The lifecycle

| Stage | Surface | Requirements |
|---|---|---|
| Find a product | `search_products`, `get_product` (service-catalogue) | RU-0007 · RU-0008 · RU-0009 |
| Place the order | `place_order` (service-orders) | RU-000A · RU-000B · RU-000C · RU-000D |
| Cancel it | `cancel_order` | RU-0003 · RU-0004 · RU-0006 |
| Or have it delivered | `record_delivery` | RU-000E · RU-000F · RU-000G · RU-000H · RU-000J |

`spec/models/MDL-order-lifecycle.statechart.json` is the same story as a machine:
`placed` splits into cancellation and shipping, a failed delivery attempt retries
or returns, and three final states close it — `cancelled`, `delivered`,
`returned`. The generated suite under `spec-conformance-tests/` is rendered from
that model, one test per transition and one per named invariant.

## Read it in this order

1. **`spec/intent/`** — three captures, verbatim and immutable: the original
   cancellation session, a browsing-and-ordering session, and a delivery session.
   Everything else is compiled from them, and every requirement's `source_ref`
   anchors into real line numbers.
2. **`spec/manifests/service-orders.manifest.yaml`** — the boundary. One entry
   per surface, both directions declared, nothing about behaviour.
3. **`spec/ru/`** — the behaviour. Notice what the statements never say: no field
   lists, no paths, no status codes, no retention window, no page limit. Those
   are manifest facts, referenced by token.
4. **`spec/manifests/shared.manifest.yaml`** — facts both services need, the
   access tiers, and the credentials behind them.

## What to look at, and why

**The lifecycle is one model, and the requirements point at it.** RU-000F says a
delivered order cannot be cancelled; the statechart says the same thing by
having no `CANCEL` transition out of `delivered`. Editing the model flips every
requirement pinned to it until `rqunit activate reaffirm` re-records the hash — a
model and the requirements verified against it cannot drift apart quietly.

**Three access tiers, three credentials, derived from one string.** An endpoint
declares `access: protected`, and the credential is whatever artifact carries
that `access_tier`. `refresh-token` is opaque, so its census is `fields: none` —
it names the credential without inventing internals it does not have.
`carrier-signature` lives in the request headers, which is why `where` exists.
`public` and `internal` are listed as `credential_free_tiers`: an open surface is
a claim, not an omission.

**Two prices the client does not get to set.** `cancel_order.refund_cents` and
`place_order.total_cents` are both `forbidden` on the request, and RU-0004 and
RU-000B say what happens when a client sends them anyway.
`ADR-refund-amount-is-server-derived` records the decision once.

**`cancel_order` declares three different side effects.** `emits` is what a
caller can be told, `audits` is evidence nobody outside sees, `publishes` is what
subscribers receive — three claims with three audiences.

**Retention lives on the audit event.** Each of the four audit events references
`{value:retention.audit_days}`; no requirement carries a "retrievable for N days"
clause, because the window is a fact rather than a behaviour.

**`access_token` carries an artifact.** The census stops at the string; the
claims live inside it, and RU-0005 addresses one of them directly —
`{artifact:access-token.iss}` — which no payload census could reach.

**`refund_settled` is an inbound message that records audit.** Billing is outside
this store (`external: true`), and handling its event writes evidence.

**`list_orders` is `planned: true`.** The facts are agreed and the code is not
written. Requirements may reference it, and conformance expects it to be absent —
which is why the run below is green with nine declared endpoints and eight
served.

## The findings are deliberate

`lint` reports one warning and `check` reports findings. They are advisory by
design, and they are here because a store with nothing to report teaches nothing
about what the tool is for.

- **L21 on RU-0002** — the constitutional audit rule asks for two mechanical
  verifications and has one. Its model suite would be the second, but
  `spec/framework/shims.yaml` registers no shim: this store ships specifications
  and no application for a subject to wrap, so the suite cannot execute and
  counts as no depth. Declared depth never exceeds provable depth.
- **C7 orphans** — `get_order`, `get_product`, `issue_session`,
  `refresh_session`, `list_orders`, the three outbound messages, and the shared
  retention value are facts no active requirement governs yet. Real stores look
  like this between sittings; the tool says so rather than staying quiet.
- **C14 on the session endpoints** — both are POSTs that record no audit event.
  HTTP method is a heuristic for mutation, so C14 reports rather than blocks:
  issuing a session is not the kind of state change the audit rule is about, and
  the judgment stays human.
- **One open GAP** — whether a customer can cancel part of a multi-item order.
  It is `clarify-later`, so it holds no activation, and it is visible data rather
  than a comment in a manifest.

## Conformance

`actual-surface.json` is what a probe would emit, hand-written because the
artifact is a committed file by design — so the demo can show CF1–CF11 without
dragging a toolchain into it. It covers both services in one file; a real
pipeline runs its extractor once per service and passes each artifact with
`--artifact`.

It deliberately spells paths as `:order_id` where the manifest writes
`{order_id}`: normalization means one route, not two divergences. And the two
session endpoints report different type names, because they serve different
shapes — CF8 reports two routes that share a type while declaring different
censuses, which is a copy-paste error it catches for free.

The boundary line at the end of the run is the honest part: some fields are
extractor-confirmed, some are not reached by extraction at all. A manifest is
allowed to exceed what a probe can see; what it may not do is let that
difference go uncounted.
