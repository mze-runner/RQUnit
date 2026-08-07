# Adapter onboarding — findings from a live consumer wiring

**Status:** written 2026-08-07, against v0.16.0-rc, after wiring the Rust adapter
into a real brownfield consumer for the first time.
**Audience:** whoever owns the adapter seam.
**Purpose:** six defects found by doing it, each with what was observed and why
it matters. Every claim below was run, not inferred from the source;
reproductions are at the end. Dated because it is a snapshot — the state it
describes is meant to stop being true.

The seam itself held. Every role ran out of process behind its pinned schema,
core invoked no toolchain, and the adapter decided nothing. What follows is
entirely about the *consumer's* path onto it, which is the half no fixture
exercises: the compliance kit proves an adapter is correct, and nothing proves a
consumer wired it correctly.

Ordered by severity.

---

## 1. A config the loader rejects passes lint, check, and doctor

The sharpest one. Put any unknown key in `[stacks.<name>.adapter]` — which is
what a pre-roles config looks like once someone moves its keys — and:

```
lint     exit 0
check    exit 0
doctor   exit 0
trace    exit 2   spec-trace: tool error: unknown [stacks.rust.adapter] key(s):
                  actual_surface, trace_diff (supported: manifest, extractor,
                  scanner, emitter, evidence, stripper)
```

The loader raises `BadConfig`. Three gates report green anyway, because they
never load the config. Only `trace` touches it, and it surfaces the problem as a
**tool error** — the class reserved for "the tool broke", not "your store is
wrong" — so a consumer's pre-commit hook running lint and check is green on a
repository whose configuration cannot be read at all.

The message itself is excellent: it names the bad keys and lists the supported
set. It is simply unreachable from the verbs a consumer runs most.

`doctor` states the assumption behind its own silence: *"lint owns config
errors; doctor does not repeat them."* Lint does not own them. Nothing does.
That premise is the defect, and it is a one-line premise to correct — whichever
verb ends up owning it, some verb a consumer runs every commit must.

## 2. An existing `rqunit.toml` has no upgrade path

A consumer config written before the adapter roles keeps validating, and
observes nothing:

```
lint     0 error(s), 0 warning(s)
check    0 error(s), 0 warning(s)
doctor   store is structurally sound.
```

That store carried `actual_surface` and `trace_diff` — both retired — and no
`[stacks.<name>.adapter]` table. Only `rqunit trace` said anything, and only
about the missing scanner.

`rqunit init` refuses a non-empty store; `--refresh-integrations` rewrites the
agent templates and deliberately does not touch `rqunit.toml`. There is no
supported way to bring a config forward. The consumer's was hand-patched, twice.

Worth considering: the treatment the agent templates got. They drifted for
exactly as long as nobody owned their delivery, and emission plus a refresh verb
fixed it. A config is harder — it carries consumer values that must survive — but
the failure mode is identical, and the diff a consumer needs is small and
mechanical.

## 3. A retired core key is indistinguishable from adapter passthrough

Left in `[stacks.<name>]` where it originally lived, `actual_surface` loads
cleanly and lands in `stack.options` beside the real adapter keys:

```
options: ['actual_surface', 'conformance_crate', 'service', 'trace_diff', 'trace_scan']
```

Nothing can say it is dead. Unknown keys under a stack are adapter-owned, and
`doctor` declines to judge passthrough without a manifest. Both of those are
correct and should stay.

But a **retired** key is the one class core can still recognise — it used to own
it. A short list of names core no longer reads, each with where it went
(`actual_surface` → `[stacks.<name>.adapter] extractor = { artifact = … }`),
turns a silent degradation into one line of instruction. It costs a constant and
a check, and it does not reopen the passthrough question.

## 4. Consumer-side wiring cannot be verified

```
$ rqunit adapter verify --stack rust        # from the consumer's root
rqunit adapter: no manifest for stack 'rust' (looked at
<consumer>/adapters/rust/adapter.yaml) — the manifest declares the roles and
kit this command verifies
```

Exit 2, correctly. `adapter verify` resolves the manifest inside the consumer,
so a consumer pointing at an installed or sibling adapter has none. That is
right for that command — it verifies an *adapter*, and the kit is the adapter's.

What is missing is the other question: **are the roles this store declares
actually runnable?** The only way this wiring was confirmed was running
`rqunit trace` and watching checks appear. `doctor` is the natural home: exec
each declared role once, report which answered. It already carries every other
"is this store wired sanely" judgment, and it is advisory, so a consumer
mid-setup is informed rather than blocked.

## 5. Distribution now blocks off-boarding, not only conformance

[`doctor.py`](../src/rqunit/doctor.py) states the gap in-code: no note is emitted
for a missing adapter manifest, because *"until adapter distribution ships a
manifest a consumer can actually point at, a finding whose fix is impossible
teaches people to ignore doctor."*

That reasoning is sound and the restraint should hold. What changed is the
stakes. The `stripper` role exists so adoption is not a one-way door — a consumer
can remove the trace annotations the framework asked them to write. A consumer
who cannot point at an adapter cannot strip, so the door closes again for
exactly the consumers distribution has not reached. Distribution is no longer
only about observing a surface; it is about being able to leave.

## 6. The only role paths that work today assume a sibling checkout

What was written into the consumer's config, and what worked:

```toml
[stacks.rust.adapter]
scanner  = { cmd = ["../rqunit/adapters/rust/target/release/scan-checks"] }
stripper = { cmd = ["../rqunit/adapters/rust/target/release/strip-annotations"] }
```

Committed to a shared repository, that path is wrong for every other developer
and for CI. `resolve_command` falls back to PATH lookup, which is the right
escape hatch — but nothing installs the binaries onto PATH, and nothing documents
PATH as the intended mode. A consumer following the scaffold's own commented
example (`adapters/rust/target/release/scan-checks`) is shown a path that exists
only inside this repository.

---

## What not to change

Two designs look like the cause and are not:

- **Core not judging adapter-owned keys.** The adapter manifest as vocabulary
  authority is correct; findings 2 and 3 are both reachable without touching it.
- **`doctor` staying silent when there is no manifest.** A finding whose fix is
  impossible does teach people to ignore doctor. Fix distribution, then the note
  becomes actionable and can be added.

## Reproducing

**Finding 1** — a rejected config passing three gates:

```bash
rm -rf /tmp/badcfg && mkdir -p /tmp/badcfg
printf '[workspace]\nmembers=[]\n' > /tmp/badcfg/Cargo.toml
rqunit init --store /tmp/badcfg
# appends under the last table, which is [stacks.rust.adapter]
printf 'actual_surface = "x.json"\n' >> /tmp/badcfg/rqunit.toml

for v in lint check doctor; do rqunit $v --store /tmp/badcfg >/dev/null 2>&1; echo "$v $?"; done
rqunit trace --store /tmp/badcfg --no-write        # the only verb that notices
```

**Findings 2 and 3** — retired keys in `[stacks.<name>]`, silent and legal: same
scaffold, but insert `actual_surface` and `trace_diff` *above* the
`[stacks.rust.adapter]` line. All four verbs stay green; the keys appear in
`stack.options`.

**Finding 4** — `rqunit adapter verify --stack <name>` from any consumer root
with no vendored adapter.
