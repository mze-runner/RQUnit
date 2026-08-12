"""Statechart dialect constraints M1–M4 and M6 (spec §6.3) — the
beyond-schema graph facts, implemented once and surfaced twice: the M lint
family reports them at `rqunit lint`, and generation refuses a model that
violates them, with the same messages.

Why late failure was not acceptable: an M1 violation was silently ignored
(nothing read `initial`); an M2 violation emitted a passing-shape test
asserting a transition to a state that does not exist, failing only at shim
runtime; an M6 duplicate rendered two tests with one name — a compile error —
and silently collapsed trace-map keys. M5 (event vocabulary resolves) is
C8's: it needs manifests, which makes it a cross-artifact question.
"""

from __future__ import annotations

from .errors import DialectViolation
from .store import Store
from .violations import Violation

M_CODES = ("M1", "M2", "M3", "M4", "M6")

# Violating these makes the RENDERED SUITE wrong — a transition to nowhere, a
# state that both ends and continues, two probes collapsed into one check
# identity — so generation refuses. M1 and M4 are modeling-quality judgments
# the plan never reads: they are reported, and do not block rendering.
REFUSES_GENERATION = ("M2", "M3", "M6")

# M4 is `warning`: a genuinely cyclic lifecycle (a reopenable order, a
# subscription) legitimately declares no final state, and M3 forbids giving a
# final one transitions out. Blocking that consumer — at lint, at generation,
# and at every unrelated activation — would teach people to bypass the gate.
SEVERITY = {"M1": "error", "M2": "error", "M3": "error",
            "M4": "warning", "M6": "error"}


def _v(code: str, store: Store, model, message: str, suggestion: str) -> Violation:
    from .lints.base import rel
    return Violation(rule=code, severity=SEVERITY[code], artifact=f"MDL-{model.id}",
                     path=rel(store, model.path), message=message,
                     suggestion=suggestion)


def dialect_violations(store: Store, only: str | None = None) -> list[Violation]:
    out: list[Violation] = []
    for model in store.models().values():
        raw = model.raw
        states: dict = raw.get("states") or {}
        initial = raw.get("initial")

        if only in (None, "M1") and initial not in states:
            out.append(_v("M1", store, model,
                          f"`initial` names '{initial}', which is not a declared state "
                          f"(states: {', '.join(sorted(states))}).",
                          "Point `initial` at a declared state, or declare it — the "
                          "machine must start somewhere real (§6.3, M1)."))

        if only in (None, "M2"):
            for state in sorted(states):
                for event, target in sorted((states[state].get("on") or {}).items()):
                    if target not in states:
                        out.append(_v("M2", store, model,
                                      f"state '{state}' transitions on {event} to "
                                      f"'{target}', which is not a declared state.",
                                      "Declare the target state or fix the transition — "
                                      "a generated test would otherwise assert a "
                                      "transition to nowhere and fail only at shim "
                                      "runtime (§6.3, M2)."))

        if only in (None, "M3"):
            for state in sorted(states):
                if states[state].get("type") == "final" and states[state].get("on"):
                    out.append(_v("M3", store, model,
                                  f"final state '{state}' declares `on` transitions — "
                                  "final means the machine is done.",
                                  "Remove the transitions or the `type: final` marker; "
                                  "a state cannot be both an end and a waypoint "
                                  "(§6.3, M3)."))

        if only in (None, "M4") and initial in states:
            # Skipped when M1 already fired: a walk with no lawful start would
            # only cascade the same defect under a second number.
            reachable = set()
            frontier = [initial]
            while frontier:
                state = frontier.pop()
                if state in reachable or state not in states:
                    continue
                reachable.add(state)
                frontier.extend((states[state].get("on") or {}).values())
            finals = {s for s in states if states[s].get("type") == "final"}
            if not finals or not (finals & reachable):
                what = ("declares no final state" if not finals
                        else f"cannot reach any final state ({', '.join(sorted(finals))}) "
                             f"from '{initial}'")
                out.append(_v("M4", store, model,
                              f"the machine {what}.",
                              "Add a reachable final state or a transition path to "
                              "one — a machine that cannot finish models a process "
                              "nobody can complete (§6.3, M4)."))

        if only in (None, "M6"):
            named: dict[str, str] = {}
            for state in sorted(states):
                invariant = states[state].get("invariant")
                if not invariant:
                    continue
                if invariant in named:
                    out.append(_v("M6", store, model,
                                  f"invariant '{invariant}' is declared on both "
                                  f"'{named[invariant]}' and '{state}' — invariant "
                                  "names are unique within a model.",
                                  "Rename one of them: each invariant generates a "
                                  "probe named after it, and two probes with one "
                                  "name collapse into one check identity "
                                  "(§6.3, M6)."))
                else:
                    named[invariant] = state
    return out


def require_sound(store: Store, model_id: str) -> None:
    """Generation's refusal: a model whose violation would make the RENDERED
    SUITE wrong must not render. Same judgments, same messages as the M lint
    family — one implementation, two surfaces. M1 and M4 are reported by the
    lint and do not block: the plan reads neither `initial` nor `type: final`,
    so refusing on them would gate rendering on a judgment rendering never
    consults."""
    problems = [v for v in dialect_violations(store)
                if v.artifact == f"MDL-{model_id}" and v.rule in REFUSES_GENERATION]
    if problems:
        lines = "\n".join(f"  [{v.rule}] {v.message} {v.suggestion}" for v in problems)
        raise DialectViolation(
            problems[0].path,
            f"MDL-{model_id} violates the statechart dialect — nothing was "
            f"generated from it:\n{lines}")
