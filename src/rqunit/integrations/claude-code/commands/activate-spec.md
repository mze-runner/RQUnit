---
description: Run Gate 1 activation for a reviewed RU batch — manual-only, like /ship. Never invoke on your own initiative; the operator runs this at the END of a Gate 1 sitting.
---

Run Gate 1 activation for: $ARGUMENTS (a FEAT id, or an explicit draft list).

This command is USER-INVOKED ONLY. Activation freezes requirements and makes
the one pipeline commit (RU framework §7.1/D-P4.7) — an agent must never
trigger it autonomously, suggest-and-run it, or re-run it after a failure
without the operator's explicit word.

Pre-flight (read-only, report before acting):
1. Confirm the Gate 1 sitting happened: the operator has reviewed the drafts
   BESIDE their INT anchors, triaged the gap list (no open `blocking` GAP may
   affect a batch member), and seen any manifest impact reports. If any of
   that is unconfirmed, STOP and present it instead of activating.
2. Show the batch: list the drafts that match $ARGUMENTS with one-line
   statements, plus `rqunit impact --against HEAD` for
   pending manifest edits (mutating changes need the operator's explicit
   --approve-impact consent).
3. `rqunit lint --format text && rqunit check --format text` must
   show 0 errors — activation refuses on red anyway; surface it early.
   Two refusals happen BEFORE anything is written, and both are worth
   surfacing here rather than mid-activation: a model that violates the
   statechart dialect (M2/M3/M6) will not render, and a store carrying models
   with no declared emitter role cannot regenerate. Either one stops the run
   with nothing mutated — but the operator should hear it at pre-flight.

Activate (only after the operator confirms the pre-flight):
   rqunit activate batch --feature $ARGUMENTS \
     --reviewer <your-handle> [--approve-impact if consented above]
   (--drafts <RU-draft-...> repeated, instead of --feature, for explicit lists.
    Reviewer ids are handles, never emails.)

Post-flight:
4. Report the draft→permanent id map the tool printed.
5. `rqunit lint --format text && rqunit trace --no-write` — green.
6. Remind the operator: flip the area's row in spec/framework/MIGRATION.md and
   tombstone the migrated legacy stories in the SAME sitting if this batch
   completes an area migration.
