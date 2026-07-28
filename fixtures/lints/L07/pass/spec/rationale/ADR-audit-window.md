# ADR-audit-window — Decision-log retention window

## Context
Decision logs must outlive the dispute window without growing unbounded.

## Decision
Retain decision logs for the shared audit window value.

## Alternatives
Indefinite retention (rejected: unbounded growth); per-service windows
(rejected: cross-service audit joins break).

## Consequences
Every retention RU references the shared value; changing the window is a
mutating manifest edit with an impact report.
