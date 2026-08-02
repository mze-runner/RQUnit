# ADR — the refund amount is derived, never accepted

## Context

An earlier client sent the refund amount in the cancellation request and the
service used it. Anyone who could call the endpoint could name their own
refund.

## Decision

`refund_cents` is `forbidden` on the cancellation request. The service derives
the amount from the order. A request carrying the field is rejected with
`validation` rather than ignored — silently dropping it would leave the caller
believing a number they supplied was honoured.

## Alternatives

Accepting the field and validating it against the order was considered and
rejected: it makes the client's number authoritative-looking, and the check is
the same work as deriving it.

## Consequences

Clients cannot preview a refund through this endpoint. If that is needed it is
a separate read surface, not a field on the write.
