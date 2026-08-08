# RQUnit — Identity scheme: segments and base-32 enumeration

**Status:** written 2026-08-08, against v0.16.0-rc. A design paper, not normative —
where this disagrees with `ru-framework-spec.md` or `formats.md`, those win. It
records decisions taken and the reasoning behind them, so that the settled parts
are not re-litigated and the open parts are visibly open.
**Audience:** whoever implements or later questions the identity scheme.
**Decision:** adopt segmented, base-32 permanent ids. Constitutional requirements
stay unsegmented. Intents are a separate question, deliberately deferred.

---

## 1. What was actually wrong

`RU-0142` is a four-digit decimal sequence, allocated store-wide at Gate 1 by
listing `spec/ru/` and taking `max + 1`. Three limits follow, and only one of
them is the one people notice first.

**Capacity.** 10,000 permanent ids. `INT-XXXX` shares the ceiling. Measured on
this repository's own stores, RU exhausts roughly 2.5× faster than INT — one
intent compiles into several RUs (§2.1, one acceptance criterion per RU) — so
RU is the binding family, not INT.

**Collision.** Two branches activating independently both compute the same
`max + 1`. The probability is not low; it is 1. The spec's answer is
organisational: activation is serialized through Gate 1 sittings, and a
`NEXT_ID` counter file is FORBIDDEN because it races under branches (§7.1).
That answer holds, but it makes concurrency a scheduling constraint rather than
a property of the design.

**Structure.** A flat sequence says nothing about what a requirement governs.
`RU-0142` and `RU-0143` may be in unrelated domains, and nothing in the id
distinguishes a store-wide constitutional invariant from a service-local rule.

Capacity is the least important of the three. It is simply the one that
announces itself with a wall.

## 2. The trilemma

An id scheme can have two of these three:

- **Readable** — short enough to say out loud in a Gate 1 sitting
- **Collision-free** under parallel allocation
- **Coordination-free** — no serialization needed to mint one

| Scheme | Readable | Collision-free | Coordination-free |
|---|---|---|---|
| `RU-0142` (today) | yes | no | no |
| `RU-A7K3` (base-32 only) | mostly | no | no |
| `RU-01K1TESTAAAA…` (ULID) | no | yes | yes |
| `RU-ORD-01A2` (segmented) | yes | across segments | across segments |

Base-32 alone answers none of the collision problem: allocation is `max + 1`,
not random, so a larger space changes nothing about two branches picking the
same next value. Segmentation is the only option that buys collision-freedom
without giving up ids humans can speak, and it multiplies capacity as a side
effect.

ULIDs are rejected for permanent ids on ergonomics, not on merit. The
framework's bet is that a human says "RU-142" in a review; `RU-01K1TESTAAAA…`
cannot be said, remembered, or transcribed. Drafts and GAPs already use ULIDs,
where that cost does not apply.

## 3. The scheme

```
RU-ORD-01A2
│  │   └── sequence: 4 Crockford base-32 characters, per segment
│  └────── segment: a domain, registered, permanent
└───────── kind
```

**Alphabet: Crockford base-32** (`0123456789ABCDEFGHJKMNPQRSTVWXYZ`), already
used in this codebase for `RU-draft-…` and `GAP-…`. It excludes I, L, O and U
precisely so they cannot be confused with 1, 0. It is ASCII-ordered, so
lexicographic sort is allocation order — `0000 → 0001 → 000Z → 0010 → 00ZZ →
0100`, and a plain `ls` lists a segment chronologically.

**Capacity: 1,048,576 per segment** in the same four characters that hold
10,000 today, multiplied again by the number of segments.

A store's first thousand ids look almost decimal (`RU-ORD-0034` is the 100th),
with letters appearing gradually. This is pleasant for adoption and carries one
trap: `RU-0142` read as decimal is 142, read as base-32 is 1,346. The existing
"never mixed widths" rule (formats §1) must become **never mixed bases**, and
it matters more, because a mixed-base store is not obviously wrong at a glance.

## 4. Segments

### 4.1 What a segment is, and what it must never become

A segment is an **allocation and ownership boundary**. It is emphatically
**not a verification boundary**, and this constraint is the most important
sentence in this paper.

C1 detects contradictions *between* RUs. C9 checks message topology *across*
services. L13 caps constitutional RUs at 15 **store-wide** — a number that is
only meaningful because it is global. If segments partitioned verification, one
domain could contradict another and nothing would notice, which is precisely
the failure a single shared store exists to prevent.

Every rule stays store-wide. Segments are invisible to all of them.

### 4.2 Which axis

The store already carries two grouping axes, and keeps them apart deliberately:

| Axis | Where it lives | Mutable |
|---|---|---|
| Logical (epic, capability) | `feature: FEAT-…`, `tags: […]` | freely |
| Physical (service, deployable) | `scope.owns`, enforced by L25 | with effort |

Both are already queryable together through `spec/projections/ru-index.json`,
which carries `feature`, `tags` and `owns` per RU. So "logical or physical" was
never the question. The question is **which axis gets welded into an immutable
id, and which stays re-cuttable metadata.**

Mint from the axis that changes slowest:

| | typical lifetime |
|---|---|
| Epic ("Q3 checkout revamp") | a quarter |
| Service (`service-orders`, later split) | a year or two |
| **Domain** ("order management") | the life of the business |

So: **segment = domain.** Epics and capabilities stay in FEAT and tags, where
re-grouping costs nothing. This also preserves the query that only metadata can
answer — "every audit-related requirement across every domain" — which an
id-borne epic would have destroyed permanently.

Segments and services are **many-to-many**. Services are deployment units;
segments are domain units. A monolith legitimately hosts three segments; one
domain legitimately spans several microservices. This is why the segment is a
**declared field**, set by the reviewer at Gate 1, not derived from
`scope.owns` — derivation would silently impose the physical axis and break on
the monolith case.

### 4.3 The one-way door

A segment name is permanent from the moment the first id is minted into it. It
lives in gate-stamp hashes, Gate 2 review directory names, committed packets,
and `verifies:` annotations inside the consumer's own source code. Renaming a
segment is not a rename; it is a mass supersession.

| Operation | tags / actors | segments |
|---|---|---|
| Add | anytime | anytime |
| Rename | re-tag the RUs | **impossible** |
| Merge | fine | **impossible** |
| Retire | fine | fine — stop allocating, ids keep working |

This asymmetry is unique among the store's vocabularies and dictates the naming
discipline: **name segments after things that outlive teams, services and
sprints.** "Order management" survives a reorg; "the Checkout squad" and
`service-orders` do not.

`segments.yaml` therefore needs a rule no other vocabulary needs: an entry with
allocated ids may be closed, never removed or renamed. The failure is silent
and permanent, so the check must exist from the first commit.

### 4.4 Segments are optional, and the absence means something

A requirement that governs everything belongs to no domain. This is not a
special case invented for the scheme — the store already has this population,
and it is exactly the constitutional tier:

```
RU-0001   constitutional   owns=[]                     feature=None
RU-0003   standard         owns=['service-orders/…']   feature=FEAT-order-cancellation
```

So:

| Requirement | Id |
|---|---|
| owns a domain | segmented — `RU-ORD-01A2` |
| owns nothing; governs the store | unsegmented — `RU-0001` |

The absence of a segment is a positive claim, readable at a glance, and
checkable: a lint mirroring L25 should report an RU whose `scope.owns` names a
segmented service but which carries no segment. Without that check,
"unsegmented" becomes the dumping ground for *I could not decide*, which is the
obvious failure mode.

Optionality also solves adoption. The framework's own principle — *"vocabularies
start empty because a seeded taxonomy nobody chose is the fastest way to a
taxonomy nobody obeys"* — argues against forcing the domain taxonomy at
`rqunit init`, the moment a consumer knows least. A store starts flat and
adopts segments when its shape is visible.

The consequence must be stated plainly: **existing ids are never rewritten.**
A store that adopts segments carries both forms permanently. Mixed ids are the
design, not a compromise being tolerated.

## 5. What this costs

**Migration of an existing store is a supersession-scale event** and should be
avoided rather than performed. `canonical_hash` covers `statement`, `scope`,
`verification` and `tier` — not the id — so re-identifying does not by itself
invalidate stamps. But the id lives in filenames, `verifies:` annotations in
consumer source, Gate 2 review directory names, and committed packets, none of
which can be rewritten without breaking history that is append-only by design.

The honest path for existing stores is therefore: **keep existing ids, allocate
new ones under the new scheme.** Which is what §4.4 already requires.

**Two live allocators.** A segmented store allocates per segment *and*
continues allocating unsegmented ids for new constitutional requirements. A new
store-wide invariant in 2028 should be `RU-0007`, not `RU-GOV-0001` — inventing
a `GOV` segment to hold cross-cutting concerns recreates the dumping ground
with a nicer name.

**Sites to change.** The four-digit assumption appears in 16 places: 6 Python
(`store.py`, `doctor.py`, `trace.py`, `cli/review.py`, `cli/activate.py`,
`lints/l04.py`) and 10 schema patterns (`ru`, `gap`, `feat`, `manifest`). All
must move together; a half-applied width is how a migration becomes permanent
damage. `ID_WIDTH` and `ID_CEILING` in `store.py` are already the single source
for the current width and should remain so.

## 6. Deliberately not decided

**Intents.** `INT-XXXX` shares the ceiling and has no allocator at all — no verb
owns intent ids, so nothing refuses at the wall; the first capture past it makes
the store unloadable. `doctor` now warns for both families, which is currently
the only guard intents have. Intents are cheap to re-identify (five files, and
`source_ref` is not in the gate stamp), and they fit the GAP profile:
numerous, machine-referenced, never spoken. Candidate schemes are ULID (follows
GAP exactly) or date-based `INT-20260808-01`, which carries the capture date —
real metadata for a verbatim record of a conversation. **Not decided here.**

**Storage organisation for concurrent work.** Segments reduce the collision
domain; they do not eliminate it. Two people in one segment still contend. That
is a separate topic and a separate paper.

**Segment granularity.** How many segments a real store wants, and whether they
track bounded contexts or something coarser, cannot be answered from inside
this repository. The scheme supports any answer; the taxonomy is the consumer's,
Gate-1-governed like every other vocabulary.

## 7. Summary of decisions

1. Permanent ids become **Crockford base-32**, four characters, sorting-stable.
2. Ids may carry a **segment**: `RU-ORD-01A2`.
3. A segment is a **domain** — the slowest-changing axis — declared, never derived.
4. Segments partition **allocation only**. Every rule stays store-wide.
5. Segments are **optional**, and absence means *store-wide*, matching the
   constitutional tier the store already has.
6. Segment names are **permanent**: add and close, never rename or merge.
7. Existing ids are **not migrated**. Mixed forms coexist by design; mixed
   *bases* never do.
8. Logical grouping stays in **FEAT and tags**, where re-cutting is free.
