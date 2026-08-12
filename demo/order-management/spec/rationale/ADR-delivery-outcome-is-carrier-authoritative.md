# ADR — the carrier's outcome is authoritative

## Context

Delivery state has two possible sources: what the carrier reports, and what the
warehouse believes it handed over. They disagree regularly — a parcel scanned as
collected can still be refused at the door — and an order that reads "delivered"
when the customer never received it is the most expensive kind of wrong state.

## Decision

Only the carrier's report moves an order to a delivered state, through
`record_delivery`. The endpoint accepts a signed request and nothing else: an
unsigned or replayed callback is rejected rather than recorded, so the audit
trail carries only outcomes a carrier is accountable for.

## Alternatives

Trusting warehouse dispatch and treating carrier reports as confirmation. It
closes orders sooner and closes some of them wrongly, and support cannot tell
which without asking the carrier anyway.

Polling the carrier's status API. It makes delivery state depend on our polling
interval, and the interval becomes a de facto requirement nobody wrote down.

## Consequences

An order can sit shipped indefinitely if a carrier never reports. That is
visible rather than hidden: the state is honest about what is known, and a
delivery that never lands is a real operational problem rather than a
bookkeeping one.
