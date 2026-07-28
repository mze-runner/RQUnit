---
name: adding-a-rule
description: The complete sequence for adding or changing an enforcement rule — a lint (L), consistency check (C), or conformance divergence (CF). Covers the module, the mandatory pass/fail fixtures, message quality, numbering, and the documentation that must move with it. Load before touching anything under src/rqunit/lints/ or src/rqunit/checks/.
---

# Adding an enforcement rule

A rule is the product. Prose describing a rule that the tool does not enforce is
drift shipped to every consumer. So a rule is not "added" until all five parts
below exist in the same change.

## What a rule may be

| Family | Scope | Lives in |
|---|---|---|
| `L*` | one artifact, judged alone or against the store | `src/rqunit/lints/` |
| `C*` | consistency BETWEEN artifacts | `src/rqunit/checks/` |
| `CF*` | manifest versus what an adapter reports about the code | `src/rqunit/conformance.py` |

Numbers are permanent. A retired rule's number is never reused — reports and
consumer suppressions refer to numbers, and reuse would silently repoint them.

## The five parts

**1. The module.** One rule per file, registered through the family's decorator.
It returns violations; it never prints, never exits, never writes.

**2. Severity, chosen deliberately.**

- `error` — the store is wrong and the build must stop.
- `warning` — real but survivable; blocks only under `--strict`. Use for
  burn-down: conditions a migrating consumer will legitimately carry for months.
- `finding` — report-only, never affects exit. Use where the tool cannot know
  whether it is a defect (orphans, ratified exceptions, suspect links).

Choosing `error` for something a healthy consumer can carry teaches people to
bypass the gate, which costs more than the rule earns.

**3. Message and suggestion.** Both mandatory, and asserted in tests. The
message states what is wrong *in the artifact's own terms*; the suggestion
states the fix and cites the governing section. Error messages are this
product's main teaching surface — a violation someone has to research is a
failure of the rule, not of the reader.

**4. Fixtures — both, always.** Under `fixtures/lints/L##/` or
`fixtures/checks/C##/`, a `pass/` store that is clean under the rule and a
`fail/` store that trips it at least twice, for that rule's reason alone. A
rule with no fail fixture is untested no matter what the suite says.

Fixture stores are minimal and generic: an order-management domain, never a
consumer's real vocabulary.

**5. Documentation, in the same change.** The rule catalogue in `HANDBOOK.md`
and the enforcement list in the specification. A rule the catalogue omits is
invisible to the humans who must satisfy it.

## Tests

The per-family harness already asserts, for every registered rule, that the
pass store is clean, the fail store is red, and both message and suggestion are
present. Add targeted tests for anything subtle — precedence, an exemption, a
false-positive class you deliberately excluded.

Assert **invariants, never counts**. Never assert an exact number of
violations, an exact id list, or that a store has no warnings. Those pass today
and break on ordinary growth, and this codebase has been bitten three times.

## Before you finish

```bash
uv run pytest                    # includes the per-family fixture harness
uv run rqunit lint --store fixtures/store/valid
uv run rqunit check --store fixtures/store/valid
```

The `valid` fixture store must stay clean under the full suite. If your new
rule reddens it, either the rule is wrong or the fixture was — decide which,
and say which in the commit message.
