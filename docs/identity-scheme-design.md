# RQUnit — The identity scheme

Why permanent ids are shaped the way they are. Not normative: where this
disagrees with [the specification](ru-framework-spec.md) or
[the formats reference](formats.md), those win — they pin the grammar, this
explains the design behind it.

---

## 1. The shape

```
RU-ORD-01A2
│  │   └── sequence: four Crockford base-32 characters, per segment
│  └────── segment: a domain — optional, registered, permanent
└───────── kind
```

**The alphabet is Crockford base-32** (`0123456789ABCDEFGHJKMNPQRSTVWXYZ`), the
same one drafts and GAPs use for their ULIDs. It excludes I, L, O and U so they
cannot be read as 1 and 0, and it ascends in ASCII order — so for a fixed width,
lexicographic sort is allocation order: `0000 → 0001 → 000Z → 0010 → 00ZZ →
0100`. A plain `ls` of `spec/ru/` lists a segment in the order it was written.

**Capacity is 1,048,576 ids per segment**, multiplied again by the number of
segments.

**A segment name** is 2–8 uppercase characters starting with a letter, and
carries exactly one prohibition: it may not be something the sequence alphabet
can spell, or `RU-CART` would read as an id whose sequence is `CART`. The
prohibition is narrow on purpose — the alphabet's own exclusions already make
`AUTH`, `ORDS`, `RISK` and `BILL` unambiguous, and refusing by length instead
would bar those four forever for a collision they cannot have.

A store reads its ids in **one base**. Nothing decodes an id to a number except
the allocator, and it decodes every id the same way.

## 2. Why not a ULID

An id scheme can have two of these three:

| | readable aloud | collision-free | coordination-free |
|---|---|---|---|
| flat sequence | yes | no | no |
| ULID | no | yes | yes |
| **segmented sequence** | yes | across segments | across segments |

Permanent ids buy readability. The framework's bet is that a human says
"RU-142" in a review, and `RU-01K1TESTAAAAAAAAAAAAAAAAAA` cannot be said,
remembered or transcribed. Drafts, GAPs and intents pay the opposite price and
carry ULIDs, because they are created outside any serialization point and
nothing could allocate them a sequence.

Permanent ids are minted at Gate 1 — the one moment the process is already
serialized — so a sequence is affordable there and nowhere else. Segments then
narrow contention further: two sittings in different domains cannot collide at
all, and two in the same one collide exactly as an add/add merge conflict, which
is visible rather than silent.

## 3. What a segment bounds, and what it must never bound

A segment is an **allocation and ownership boundary**. It is emphatically **not
a verification boundary**, and this is the most important sentence here.

C1 detects contradictions *between* RUs. C9 checks message topology *across*
services. L13 caps constitutional RUs at 15 **store-wide** — a number that is
only meaningful because it is global. If segments partitioned verification, one
domain could contradict another and nothing would notice, which is precisely the
failure a single shared store exists to prevent.

Every rule is store-wide. Segments are invisible to all of them.

## 4. Why a segment is a domain

The store carries three grouping axes and keeps them apart deliberately:

| Axis | Where it lives | Re-cuttable |
|---|---|---|
| Capability (epic, feature) | `feature`, `tags` | freely |
| Deployable (service) | `scope.owns` | with effort |
| Domain | the id's segment | never |

All three are queryable from `spec/projections/ru-index.json`, so the question
was never "which axis do we group by" — it is **which axis gets welded into an
immutable id**. Mint from the one that changes slowest:

| | typical lifetime |
|---|---|
| Epic ("Q3 checkout revamp") | a quarter |
| Service (`service-orders`, later split) | a year or two |
| **Domain** ("order management") | the life of the business |

So a segment is a domain. Capabilities stay in `feature` and `tags`, where
re-grouping costs nothing and a query like "every audit-related requirement
across every domain" still works — a query an id-borne epic would have destroyed
permanently.

Segments and services are **many-to-many**: services are deployment units,
segments are domain units. A monolith legitimately hosts three segments; one
domain legitimately spans several services. That is why a draft **declares** its
segment and the framework never derives one from `scope.owns` — derivation would
silently impose the deployable axis and be wrong on both shapes.

## 5. Permanence

A segment name is permanent from the moment its first id is minted. It lives in
gate-stamp hashes, Gate 2 review directory names, committed packets, and
`verifies:` annotations inside the consumer's own source. Renaming one is not a
rename; it is a mass supersession.

| Operation | tags / actors | segments |
|---|---|---|
| Add | anytime | anytime |
| Rename | re-tag the RUs | **impossible** |
| Merge | fine | **impossible** |
| Retire | fine | fine — close it; its ids keep working |

This asymmetry is unique among the store's vocabularies, and it dictates the
naming discipline: **name a segment after something that outlives teams,
services and sprints.** "Order management" survives a reorganisation; "the
checkout squad" and `service-orders` do not.

`segments.yaml` therefore needs a rule no other vocabulary needs — an entry with
allocated ids may be closed, never removed or renamed — and C16 enforces it,
because the failure is silent and cannot be undone.

## 6. Segments are optional, and absence is a claim

A requirement that governs everything belongs to no domain, and that population
is exactly the constitutional tier: the schema requires `scope.owns` for every
other tier and lets constitutional omit it, so "governs everything" and "owns
nothing in particular" are already the same claim.

| Requirement | Id |
|---|---|
| governs a domain | segmented — `RU-ORD-01A2` |
| governs the store | unsegmented — `RU-0001` |

The absence of a segment is a positive claim, readable at a glance, and checked:
L27 reports a draft whose declaration contradicts its tier, in either direction —
a standard draft naming no segment, or a constitutional draft naming one. Without
that check, "unsegmented" becomes the dumping ground for *I could not decide*,
and a cross-cutting `GOV` segment is the same dumping ground under a better name.

Optionality is also what makes adoption honest. Vocabularies start empty here,
because a taxonomy chosen when a consumer knows least is the fastest route to a
taxonomy nobody obeys. A store runs flat until its shape is visible, then adopts
segments; ids minted before that keep their unsegmented form permanently, which
is the design rather than a compromise.

## 7. Open

**Storage organisation for concurrent work.** Segments reduce the collision
domain; they do not eliminate it. Two people working in one segment still
contend, and that is a separate question.

**Segment granularity.** How many segments a store wants, and whether they track
bounded contexts or something coarser, cannot be answered from inside this
repository. The scheme supports any answer; the taxonomy is the consumer's,
Gate-1-governed like every other vocabulary.
